"""
Router: inventario general

  GET  /shortages
  GET  /reorder-suggestions
  GET  /unmatched-receipts
  POST /unmatched-receipts/{id}/resolve
  POST /issues
  POST /transfers
  POST /counts
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import (
    InventoryMovement,
    Part,
    Reservation,
    Shortage,
    UnmatchedReceipt,
    WorkOrder,
    get_db,
)
from app.models.schemas import (
    CountRequest,
    IssueRequest,
    MovementCreatedResponse,
    ReorderSuggestionResponse,
    ResolveOkResponse,
    ResolveUnmatchedReceiptRequest,
    ShortageResponse,
    TransferRequest,
    UnmatchedReceiptResponse,
)
from app.services import kafka_producer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["inventory"])


# ── GET /shortages ─────────────────────────────────────────────────────────────

@router.get(
    "/shortages",
    response_model=list[ShortageResponse],
    summary="Faltantes activos detectados",
)
async def get_shortages(
    work_order_id: Optional[int] = Query(None),
    part_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[ShortageResponse]:
    q = select(Shortage).where(Shortage.status == "open")
    if work_order_id is not None:
        q = q.where(Shortage.work_order_id == work_order_id)
    if part_id is not None:
        q = q.where(Shortage.part_id == part_id)
    q = q.order_by(Shortage.created_at.asc())

    rows = (await db.execute(q)).scalars().all()
    return [
        ShortageResponse(
            shortage_id=s.shortage_id,
            work_order_id=s.work_order_id,
            part_id=s.part_id,
            name=s.name,
            missing_quantity=s.missing_quantity,
            status=s.status,
            created_at=s.created_at,
        )
        for s in rows
    ]


# ── GET /reorder-suggestions ───────────────────────────────────────────────────

@router.get(
    "/reorder-suggestions",
    response_model=list[ReorderSuggestionResponse],
    summary="Sugerencias de reabastecimiento",
)
async def get_reorder_suggestions(
    db: AsyncSession = Depends(get_db),
) -> list[ReorderSuggestionResponse]:
    # Agrupa faltantes abiertos por part_id para calcular la cantidad sugerida
    rows = (await db.execute(
        select(
            Shortage.part_id,
            func.sum(Shortage.missing_quantity).label("total_missing"),
        )
        .where(Shortage.status == "open", Shortage.part_id.isnot(None))
        .group_by(Shortage.part_id)
        .order_by(func.sum(Shortage.missing_quantity).desc())
    )).all()

    suggestions: list[ReorderSuggestionResponse] = []
    for row in rows:
        part = await db.get(Part, row.part_id)
        if not part:
            continue

        # OTs afectadas
        wo_ids_result = (await db.execute(
            select(Shortage.work_order_id)
            .where(Shortage.part_id == row.part_id, Shortage.status == "open")
            .distinct()
        )).scalars().all()

        suggestions.append(ReorderSuggestionResponse(
            part_id=part.part_id,
            name=part.name,
            sku=part.sku,
            suggested_quantity=float(row.total_missing or 0),
            work_order_ids=list(wo_ids_result),
        ))

    return suggestions


# ── GET /unmatched-receipts ────────────────────────────────────────────────────

@router.get(
    "/unmatched-receipts",
    response_model=list[UnmatchedReceiptResponse],
    summary="Recepciones sin coincidencia en catálogo",
)
async def get_unmatched_receipts(
    db: AsyncSession = Depends(get_db),
) -> list[UnmatchedReceiptResponse]:
    rows = (await db.execute(
        select(UnmatchedReceipt)
        .where(UnmatchedReceipt.status == "pending")
        .order_by(UnmatchedReceipt.received_at.asc())
    )).scalars().all()

    return [
        UnmatchedReceiptResponse(
            id=r.id,
            purchase_line_id=r.purchase_line_id,
            part_number=r.part_number,
            description=r.description,
            quantity=r.quantity,
            work_order_code=r.work_order_code,
            status=r.status,
            received_at=r.received_at,
        )
        for r in rows
    ]


# ── POST /unmatched-receipts/{id}/resolve ──────────────────────────────────────

@router.post(
    "/unmatched-receipts/{receipt_id}/resolve",
    response_model=ResolveOkResponse,
    summary="Resolver manualmente una recepción sin coincidencia",
)
async def resolve_unmatched_receipt(
    receipt_id: int,
    body: ResolveUnmatchedReceiptRequest,
    db: AsyncSession = Depends(get_db),
) -> ResolveOkResponse:
    receipt = await db.get(UnmatchedReceipt, receipt_id)
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Recepción no encontrada")
    if receipt.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"La recepción ya fue procesada (status={receipt.status})")

    part = await db.get(Part, body.part_id)
    if not part:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Pieza destino no encontrada")

    # Actualizar recepción
    await db.execute(
        update(UnmatchedReceipt)
        .where(UnmatchedReceipt.id == receipt_id)
        .values(status="resolved", resolved_part_id=body.part_id)
    )

    # Entrada en ledger
    location_id = settings.DEFAULT_STOCK_LOCATION_ID
    movement = InventoryMovement(
        part_id=body.part_id,
        location_id=location_id,
        delta=receipt.quantity,
        movement_type="received",
        reference_id=str(receipt.purchase_line_id),
        created_at=datetime.now(timezone.utc),
    )
    db.add(movement)
    await db.flush()

    await kafka_producer.publish(
        "stock.received",
        data={
            "part_id": body.part_id,
            "location_id": location_id,
            "quantity": receipt.quantity,
            "unit_cost": receipt.unit_price,
            "currency": receipt.currency,
            "purchase_line_id": receipt.purchase_line_id,
        },
        key=f"part:{body.part_id}",
    )

    await db.commit()
    return ResolveOkResponse(ok=True)


# ── POST /issues ───────────────────────────────────────────────────────────────

@router.post(
    "/issues",
    response_model=MovementCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Despacho de material a una orden de trabajo",
)
async def post_issue(
    body: IssueRequest,
    db: AsyncSession = Depends(get_db),
) -> MovementCreatedResponse:
    # Verificar OT
    wo = (await db.execute(
        select(WorkOrder)
        .where(WorkOrder.code == body.work_order_code, WorkOrder.deleted == False)
    )).scalar_one_or_none()
    if not wo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Orden de trabajo no encontrada")

    # Verificar pieza
    part = await db.get(Part, body.part_id)
    if not part:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Pieza no encontrada")

    # Calcular on_hand en la ubicación específica
    on_hand_loc = float((await db.execute(
        select(func.coalesce(func.sum(InventoryMovement.delta), 0.0))
        .where(
            InventoryMovement.part_id == body.part_id,
            InventoryMovement.location_id == body.location_id,
        )
    )).scalar_one())

    # Reservas activas globales de la pieza
    total_reserved = float((await db.execute(
        select(func.coalesce(func.sum(Reservation.quantity), 0.0))
        .where(Reservation.part_id == body.part_id, Reservation.status == "active")
    )).scalar_one())

    available = max(0.0, on_hand_loc - total_reserved)

    if available < body.quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stock insuficiente: disponible={available:.2f}, "
                f"solicitado={body.quantity:.2f}"
            ),
        )

    # Registrar salida en ledger (delta negativo)
    movement = InventoryMovement(
        part_id=body.part_id,
        location_id=body.location_id,
        delta=-body.quantity,
        movement_type="issued",
        reference_id=body.work_order_code,
        created_at=datetime.now(timezone.utc),
    )
    db.add(movement)
    await db.flush()

    # Marcar reserva activa como fulfilled (la más antigua primero)
    active_res = (await db.execute(
        select(Reservation)
        .where(
            Reservation.work_order_id == wo.work_order_id,
            Reservation.part_id == body.part_id,
            Reservation.status == "active",
        )
        .order_by(Reservation.created_at.asc())
        .limit(1)
        .with_for_update()
    )).scalar_one_or_none()

    if active_res:
        await db.execute(
            update(Reservation)
            .where(Reservation.reservation_id == active_res.reservation_id)
            .values(status="fulfilled", updated_at=datetime.now(timezone.utc))
        )

    await kafka_producer.publish(
        "stock.issued",
        data={
            "work_order_id": wo.work_order_id,
            "part_id": body.part_id,
            "location_id": body.location_id,
            "quantity": body.quantity,
            "issued_by": body.issued_by,
        },
        key=f"part:{body.part_id}",
    )

    await db.commit()
    return MovementCreatedResponse(movement_id=movement.movement_id)


# ── POST /transfers ────────────────────────────────────────────────────────────

@router.post(
    "/transfers",
    response_model=MovementCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Transferir stock entre ubicaciones",
)
async def post_transfer(
    body: TransferRequest,
    db: AsyncSession = Depends(get_db),
) -> MovementCreatedResponse:
    part = await db.get(Part, body.part_id)
    if not part:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pieza no encontrada")

    # on_hand en origen
    on_hand_src = float((await db.execute(
        select(func.coalesce(func.sum(InventoryMovement.delta), 0.0))
        .where(
            InventoryMovement.part_id == body.part_id,
            InventoryMovement.location_id == body.from_location_id,
        )
    )).scalar_one())

    # Reservas activas de la pieza
    total_reserved = float((await db.execute(
        select(func.coalesce(func.sum(Reservation.quantity), 0.0))
        .where(Reservation.part_id == body.part_id, Reservation.status == "active")
    )).scalar_one())

    available_src = max(0.0, on_hand_src - total_reserved)

    if available_src < body.quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Stock insuficiente en origen: disponible={available_src:.2f}, "
                f"solicitado={body.quantity:.2f}"
            ),
        )

    ref = f"{body.from_location_id}→{body.to_location_id}"
    now = datetime.now(timezone.utc)

    # Salida del origen
    mov_out = InventoryMovement(
        part_id=body.part_id,
        location_id=body.from_location_id,
        delta=-body.quantity,
        movement_type="transferred",
        reference_id=ref,
        created_at=now,
    )
    # Entrada al destino
    mov_in = InventoryMovement(
        part_id=body.part_id,
        location_id=body.to_location_id,
        delta=body.quantity,
        movement_type="transferred",
        reference_id=ref,
        created_at=now,
    )
    db.add_all([mov_out, mov_in])
    await db.flush()

    await kafka_producer.publish(
        "stock.transferred",
        data={
            "part_id": body.part_id,
            "from_location_id": body.from_location_id,
            "to_location_id": body.to_location_id,
            "quantity": body.quantity,
        },
        key=f"part:{body.part_id}",
    )

    await db.commit()
    return MovementCreatedResponse(movement_id=mov_out.movement_id)


# ── POST /counts ───────────────────────────────────────────────────────────────

@router.post(
    "/counts",
    response_model=MovementCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar conteo cíclico (ajuste de inventario)",
)
async def post_count(
    body: CountRequest,
    db: AsyncSession = Depends(get_db),
) -> MovementCreatedResponse:
    part = await db.get(Part, body.part_id)
    if not part:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pieza no encontrada")

    # Calcular on_hand actual en la ubicación
    current_on_hand = float((await db.execute(
        select(func.coalesce(func.sum(InventoryMovement.delta), 0.0))
        .where(
            InventoryMovement.part_id == body.part_id,
            InventoryMovement.location_id == body.location_id,
        )
    )).scalar_one())

    delta = body.counted_quantity - current_on_hand

    # Si delta == 0 no hay ajuste que registrar
    if abs(delta) < 1e-9:
        # Devuelve un ID ficticio; sin cambios en ledger
        return MovementCreatedResponse(movement_id=0)

    movement = InventoryMovement(
        part_id=body.part_id,
        location_id=body.location_id,
        delta=delta,
        movement_type="adjusted",
        reference_id=body.reason,
        created_at=datetime.now(timezone.utc),
    )
    db.add(movement)
    await db.flush()

    await kafka_producer.publish(
        "stock.adjusted",
        data={
            "part_id": body.part_id,
            "location_id": body.location_id,
            "delta": delta,
            "reason": body.reason,
        },
        key=f"part:{body.part_id}",
    )

    await db.commit()
    return MovementCreatedResponse(movement_id=movement.movement_id)
