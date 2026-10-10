from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.models import (
    InventoryMovement,
    Location,
    Part,
    Reservation,
    Shortage,
    UnmatchedReceipt,
    WorkOrder,
    BomLine,
)
from app.schemas.inventory import (
    AdjustmentItem,
    AvailabilityResponse,
    CountRequest,
    CountResponse,
    IssueRequest,
    LedgerEntry,
    LedgerResponse,
    LocationAvailability,
    MaterialLine,
    MovementResponse,
    ReorderSuggestionItem,
    ReorderSuggestionsResponse,
    ResolveReceiptRequest,
    ShortageItem,
    ShortagesListResponse,
    TransferRequest,
    UnmatchedReceiptItem,
    UnmatchedReceiptsResponse,
    WorkOrderMaterialsResponse,
)

router = APIRouter(tags=["inventario"])


# ── 1. GET /parts/{part_id}/availability ─────────────────────────────────────
@router.get(
    "/parts/{part_id}/availability",
    response_model=AvailabilityResponse,
    summary="Saldo de una pieza, total y por ubicación",
)
async def get_part_availability(part_id: int, db: AsyncSession = Depends(get_db)):
    # Verificar si la pieza existe
    part_query = await db.execute(select(Part).where(Part.part_id == part_id))
    part = part_query.scalar_one_or_none()
    if not part:
        raise HTTPException(status_code=404, detail=f"Pieza {part_id} no encontrada")

    # Saldo total (on_hand = SUM(quantity))
    soh_q = await db.execute(
        select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
            InventoryMovement.part_id == part_id
        )
    )
    total_on_hand = soh_q.scalar() or 0

    # Total reservado activo
    res_q = await db.execute(
        select(func.coalesce(func.sum(Reservation.quantity), 0)).where(
            Reservation.part_id == part_id,
            Reservation.status == "active",
        )
    )
    total_reserved = res_q.scalar() or 0
    total_available = total_on_hand - total_reserved

    # Saldo por ubicación
    loc_soh_q = await db.execute(
        select(
            InventoryMovement.location_id,
            func.coalesce(func.sum(InventoryMovement.quantity), 0).label("on_hand"),
        )
        .where(InventoryMovement.part_id == part_id)
        .group_by(InventoryMovement.location_id)
    )
    loc_stock = {row[0]: row[1] for row in loc_soh_q.fetchall()}

    # Obtener todas las ubicaciones conocidas
    locs_q = await db.execute(select(Location))
    all_locs = locs_q.scalars().all()

    locations_list = []
    for loc in all_locs:
        on_hand_loc = loc_stock.get(loc.location_id, 0)
        # Según OpenAPI: las reservas son globales, reportar reserved=0 por estante
        locations_list.append(
            LocationAvailability(
                location_id=loc.location_id,
                code=loc.code,
                on_hand=on_hand_loc,
                reserved=0,
                available=on_hand_loc,
            )
        )

    return AvailabilityResponse(
        part_id=part_id,
        on_hand=total_on_hand,
        reserved=total_reserved,
        available=total_available,
        locations=locations_list,
    )


# ── 2. GET /parts/{part_id}/ledger ───────────────────────────────────────────
@router.get(
    "/parts/{part_id}/ledger",
    response_model=LedgerResponse,
    summary="Kardex de una pieza",
)
async def get_part_ledger(part_id: int, db: AsyncSession = Depends(get_db)):
    part_query = await db.execute(select(Part).where(Part.part_id == part_id))
    if not part_query.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Pieza {part_id} no encontrada")

    # Movimientos ordenados del más reciente al más antiguo
    moves_q = await db.execute(
        select(InventoryMovement)
        .where(InventoryMovement.part_id == part_id)
        .order_by(InventoryMovement.occurred_at.asc(), InventoryMovement.movement_id.asc())
    )
    all_moves = moves_q.scalars().all()

    # Calcular saldo acumulado paso a paso
    running_balance = 0
    entries_asc = []
    for m in all_moves:
        running_balance += m.quantity
        entries_asc.append(
            LedgerEntry(
                movement_id=m.movement_id,
                type=m.type,
                part_id=m.part_id,
                location_id=m.location_id,
                quantity=m.quantity,
                occurred_at=m.occurred_at,
                reference=m.reference,
                balance=running_balance,
            )
        )

    # El contrato exige devolver del más reciente al más antiguo
    return LedgerResponse(part_id=part_id, entries=list(reversed(entries_asc)))


# ── 3. GET /work-orders/{code}/materials ─────────────────────────────────────
@router.get(
    "/work-orders/{code}/materials",
    response_model=WorkOrderMaterialsResponse,
    summary="Materiales de una orden",
)
async def get_work_order_materials(code: str, db: AsyncSession = Depends(get_db)):
    wo_q = await db.execute(select(WorkOrder).where(WorkOrder.code == code))
    wo = wo_q.scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=404, detail=f"Orden {code} no encontrada")

    # Líneas reservadas de la orden
    res_q = await db.execute(
        select(Reservation).where(Reservation.work_order_id == wo.work_order_id)
    )
    reservations = res_q.scalars().all()

    # Faltantes de la orden
    short_q = await db.execute(
        select(Shortage).where(
            Shortage.work_order_id == wo.work_order_id,
            Shortage.status == "open",
        )
    )
    shortages = short_q.scalars().all()

    lines = []
    # Mapear reservas
    for r in reservations:
        lines.append(
            MaterialLine(
                inspection_item_id=r.inspection_item_id or 0,
                bom_line_id=r.bom_line_id or 0,
                part_id=r.part_id,
                name="",
                required=r.quantity,
                reserved=r.quantity if r.status == "active" else 0,
                issued=r.quantity if r.status == "fulfilled" else 0,
                missing=0,
            )
        )
    # Mapear faltantes
    for s in shortages:
        lines.append(
            MaterialLine(
                inspection_item_id=s.inspection_item_id or 0,
                bom_line_id=s.bom_line_id or 0,
                part_id=s.part_id,
                name=s.name,
                required=s.missing_quantity,
                reserved=0,
                issued=0,
                missing=s.missing_quantity,
            )
        )

    return WorkOrderMaterialsResponse(
        work_order_id=wo.work_order_id,
        code=wo.code,
        lines=lines,
    )


# ── 4. GET /shortages ────────────────────────────────────────────────────────
@router.get(
    "/shortages",
    response_model=ShortagesListResponse,
    summary="Faltantes abiertos",
)
async def get_shortages(
    work_order_code: Optional[str] = Query(None),
    part_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Shortage).where(Shortage.status == "open")
    if work_order_code:
        stmt = stmt.where(Shortage.work_order_code == work_order_code)
    if part_id:
        stmt = stmt.where(Shortage.part_id == part_id)

    res = await db.execute(stmt)
    shortages = res.scalars().all()

    return ShortagesListResponse(
        items=[
            ShortageItem(
                work_order_id=s.work_order_id,
                work_order_code=s.work_order_code or "",
                part_id=s.part_id,
                name=s.name,
                missing_quantity=s.missing_quantity,
                inspection_item_id=s.inspection_item_id or 0,
                opened_at=s.opened_at,
            )
            for s in shortages
        ]
    )


# ── 5. GET /reorder-suggestions ──────────────────────────────────────────────
@router.get(
    "/reorder-suggestions",
    response_model=ReorderSuggestionsResponse,
    summary="Sugerencias de compra vigentes",
)
async def get_reorder_suggestions(db: AsyncSession = Depends(get_db)):
    # Agrupar faltantes por pieza
    res = await db.execute(
        select(Shortage).where(Shortage.status == "open", Shortage.part_id.isnot(None))
    )
    shortages = res.scalars().all()

    grouped = {}
    for s in shortages:
        pid = s.part_id
        if pid not in grouped:
            grouped[pid] = {
                "name": s.name,
                "missing_sum": 0,
                "work_order_ids": set(),
            }
        grouped[pid]["missing_sum"] += s.missing_quantity or 0
        grouped[pid]["work_order_ids"].add(s.work_order_id)

    items = []
    for pid, data in grouped.items():
        part_q = await db.execute(select(Part).where(Part.part_id == pid))
        part = part_q.scalar_one_or_none()
        items.append(
            ReorderSuggestionItem(
                part_id=pid,
                sku=part.sku if part else None,
                name=data["name"],
                suggested_quantity=max(1, data["missing_sum"]),
                work_order_ids=list(data["work_order_ids"]),
            )
        )

    return ReorderSuggestionsResponse(items=items)


# ── 6. GET /unmatched-receipts ───────────────────────────────────────────────
@router.get(
    "/unmatched-receipts",
    response_model=UnmatchedReceiptsResponse,
    summary="Recepciones sin relacionar",
)
async def get_unmatched_receipts(db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(UnmatchedReceipt).where(UnmatchedReceipt.status == "pending")
    )
    receipts = res.scalars().all()

    return UnmatchedReceiptsResponse(
        items=[
            UnmatchedReceiptItem(
                id=r.id,
                purchase_line_id=r.purchase_line_id,
                part_number=r.part_number,
                description=r.description or "",
                quantity=r.quantity,
                unit_price=str(r.unit_price) if r.unit_price else None,
                currency=r.currency,
                received_at=r.received_at,
                work_order_code=r.work_order_code,
            )
            for r in receipts
        ]
    )


# ── 7. POST /issues (Salida por escaneo en piso) ─────────────────────────────
@router.post(
    "/issues",
    status_code=status.HTTP_201_CREATED,
    response_model=MovementResponse,
    summary="Salida de material contra orden",
)
async def issue_part(req: IssueRequest, db: AsyncSession = Depends(get_db)):
    # 1. Verificar saldo en la ubicación específica
    stock_q = await db.execute(
        select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
            InventoryMovement.part_id == req.part_id,
            InventoryMovement.location_id == req.location_id,
        )
    )
    location_on_hand = stock_q.scalar() or 0

    if location_on_hand < req.quantity:
        raise HTTPException(
            status_code=409,
            detail=f"Saldo insuficiente en ubicación {req.location_id}. Disponible: {location_on_hand}, requerido: {req.quantity}",
        )

    # 2. Registrar movimiento de salida (negativo)
    movement = InventoryMovement(
        type="issue",
        part_id=req.part_id,
        location_id=req.location_id,
        quantity=-req.quantity,
        occurred_at=func.now(),
        reference=req.work_order_code,
    )
    db.add(movement)

    # 3. Consumir reserva activa si existe
    wo_q = await db.execute(select(WorkOrder).where(WorkOrder.code == req.work_order_code))
    wo = wo_q.scalar_one_or_none()
    if wo:
        res_q = await db.execute(
            select(Reservation).where(
                Reservation.work_order_id == wo.work_order_id,
                Reservation.part_id == req.part_id,
                Reservation.status == "active",
            )
        )
        res_obj = res_q.scalars().first()
        if res_obj:
            if res_obj.quantity <= req.quantity:
                res_obj.status = "fulfilled"
            else:
                res_obj.quantity -= req.quantity

    await db.commit()
    await db.refresh(movement)

    return MovementResponse(
        movement_id=movement.movement_id,
        type=movement.type,
        part_id=movement.part_id,
        location_id=movement.location_id,
        quantity=movement.quantity,
        occurred_at=movement.occurred_at,
        reference=movement.reference,
    )


# ── 8. POST /transfers (Transferencia entre ubicaciones) ──────────────────────
@router.post(
    "/transfers",
    status_code=status.HTTP_201_CREATED,
    response_model=MovementResponse,
    summary="Transferencia entre ubicaciones",
)
async def transfer_part(req: TransferRequest, db: AsyncSession = Depends(get_db)):
    # Verificar saldo en origen
    stock_q = await db.execute(
        select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
            InventoryMovement.part_id == req.part_id,
            InventoryMovement.location_id == req.from_location_id,
        )
    )
    origin_stock = stock_q.scalar() or 0

    if origin_stock < req.quantity:
        raise HTTPException(
            status_code=409,
            detail=f"Saldo insuficiente en origen {req.from_location_id}. Disponible: {origin_stock}",
        )

    # Registrar salida de origen
    mov_out = InventoryMovement(
        type="transfer_out",
        part_id=req.part_id,
        location_id=req.from_location_id,
        quantity=-req.quantity,
        occurred_at=func.now(),
        reference=f"Transfer to {req.to_location_id}",
    )
    # Registrar entrada en destino
    mov_in = InventoryMovement(
        type="transfer_in",
        part_id=req.part_id,
        location_id=req.to_location_id,
        quantity=req.quantity,
        occurred_at=func.now(),
        reference=f"Transfer from {req.from_location_id}",
    )
    db.add(mov_out)
    db.add(mov_in)
    await db.commit()
    await db.refresh(mov_in)

    return MovementResponse(
        movement_id=mov_in.movement_id,
        type=mov_in.type,
        part_id=mov_in.part_id,
        location_id=mov_in.location_id,
        quantity=mov_in.quantity,
        occurred_at=mov_in.occurred_at,
        reference=mov_in.reference,
    )


# ── 9. POST /counts (Conteo físico de inventario) ────────────────────────────
@router.post(
    "/counts",
    status_code=status.HTTP_201_CREATED,
    response_model=CountResponse,
    summary="Conteo cíclico con ajustes",
)
async def cycle_count(req: CountRequest, db: AsyncSession = Depends(get_db)):
    if not req.reason.strip():
        raise HTTPException(status_code=422, detail="El motivo del ajuste es obligatorio")

    adjustments = []
    for line in req.lines:
        # Saldo actual en esa ubicación
        stk_q = await db.execute(
            select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
                InventoryMovement.part_id == line.part_id,
                InventoryMovement.location_id == req.location_id,
            )
        )
        current_qty = stk_q.scalar() or 0
        delta = line.counted_quantity - current_qty

        if delta != 0:
            adj_mov = InventoryMovement(
                type="adjustment",
                part_id=line.part_id,
                location_id=req.location_id,
                quantity=delta,
                occurred_at=func.now(),
                reference=req.reason,
            )
            db.add(adj_mov)
            adjustments.append(AdjustmentItem(part_id=line.part_id, delta=delta))

    await db.commit()
    return CountResponse(adjustments=adjustments)


# ── 10. POST /unmatched-receipts/{id}/resolve ────────────────────────────────
@router.post(
    "/unmatched-receipts/{receipt_id}/resolve",
    status_code=status.HTTP_200_OK,
    response_model=MovementResponse,
    summary="Relacionar a mano una recepción con una pieza",
)
async def resolve_unmatched_receipt(
    receipt_id: int,
    req: ResolveReceiptRequest,
    db: AsyncSession = Depends(get_db),
):
    receipt_q = await db.execute(
        select(UnmatchedReceipt).where(UnmatchedReceipt.id == receipt_id)
    )
    receipt = receipt_q.scalar_one_or_none()
    if not receipt:
        raise HTTPException(status_code=404, detail="Recepción no encontrada")
    if receipt.status == "resolved":
        raise HTTPException(status_code=409, detail="La recepción ya fue resuelta")

    # Ubicación por defecto U-100 (100) si no se especifica
    loc_id = req.location_id or 100

    # Marcar como resuelta
    receipt.status = "resolved"
    receipt.resolved_part_id = req.part_id

    # Registrar entrada en el libro mayor
    receipt_mov = InventoryMovement(
        type="receipt",
        part_id=req.part_id,
        location_id=loc_id,
        quantity=receipt.quantity,
        occurred_at=func.now(),
        reference=f"Resolved purchase line {receipt.purchase_line_id}",
        purchase_line_id=receipt.purchase_line_id,
    )
    db.add(receipt_mov)
    await db.commit()
    await db.refresh(receipt_mov)

    return MovementResponse(
        movement_id=receipt_mov.movement_id,
        type=receipt_mov.type,
        part_id=receipt_mov.part_id,
        location_id=receipt_mov.location_id,
        quantity=receipt_mov.quantity,
        occurred_at=receipt_mov.occurred_at,
        reference=receipt_mov.reference,
    )