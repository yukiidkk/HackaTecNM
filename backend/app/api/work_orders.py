"""
Router: /work-orders

  GET /work-orders/{code}/materials — desglose de materiales por OT
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (
    InventoryMovement,
    Reservation,
    Shortage,
    WorkOrder,
    get_db,
)
from app.models.schemas import WorkOrderMaterialLine, WorkOrderMaterialsResponse

router = APIRouter(prefix="/work-orders", tags=["work-orders"])


@router.get(
    "/{code}/materials",
    response_model=WorkOrderMaterialsResponse,
    summary="Materiales (reservas, entregas, faltantes) de una OT",
)
async def get_work_order_materials(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> WorkOrderMaterialsResponse:
    wo = (await db.execute(
        select(WorkOrder)
        .where(WorkOrder.code == code, WorkOrder.deleted == False)
    )).scalar_one_or_none()

    if not wo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Orden de trabajo '{code}' no encontrada")

    # Reservas activas y cumplidas (fulfilled)
    reservations = (await db.execute(
        select(Reservation)
        .where(
            Reservation.work_order_id == wo.work_order_id,
            Reservation.status.in_(["active", "fulfilled"]),
        )
    )).scalars().all()

    # Faltantes activos de la OT
    shortages = (await db.execute(
        select(Shortage)
        .where(
            Shortage.work_order_id == wo.work_order_id,
            Shortage.status == "open",
        )
    )).scalars().all()

    # Movimientos de tipo 'issued' referenciados por la OT
    issued_movements = (await db.execute(
        select(InventoryMovement)
        .where(
            InventoryMovement.reference_id == code,
            InventoryMovement.movement_type == "issued",
        )
    )).scalars().all()

    # Índice de entregado por part_id
    delivered_by_part: dict[int, float] = {}
    for mov in issued_movements:
        delivered_by_part[mov.part_id] = (
            delivered_by_part.get(mov.part_id, 0.0) + abs(mov.delta)
        )

    # Construir líneas — una por inspection_item_id único
    lines: list[WorkOrderMaterialLine] = []
    seen_item_ids: set[int] = set()

    for res in reservations:
        iid = res.inspection_item_id or 0
        if iid in seen_item_ids:
            continue
        seen_item_ids.add(iid)

        delivered = delivered_by_part.get(res.part_id, 0.0)
        lines.append(WorkOrderMaterialLine(
            inspection_item_id=iid,
            bom_line_id=None,
            part_id=res.part_id,
            name="",           # nombre resuelto en siguiente paso
            reserved=res.quantity if res.status == "active" else 0.0,
            delivered=delivered,
            shortage=None,
        ))

    for sh in shortages:
        iid = sh.inspection_item_id or 0
        if iid in seen_item_ids:
            continue
        seen_item_ids.add(iid)

        lines.append(WorkOrderMaterialLine(
            inspection_item_id=iid,
            bom_line_id=None,
            part_id=sh.part_id,
            name=sh.name,
            reserved=0.0,
            delivered=delivered_by_part.get(sh.part_id, 0.0) if sh.part_id else 0.0,
            shortage=sh.missing_quantity,
        ))

    # Resolver nombres de partes para líneas sin nombre
    from app.core.database import Part
    part_ids = {ln.part_id for ln in lines if ln.part_id}
    if part_ids:
        parts = (await db.execute(
            select(Part).where(Part.part_id.in_(part_ids))
        )).scalars().all()
        name_map = {p.part_id: p.name for p in parts}
        for ln in lines:
            if not ln.name and ln.part_id:
                ln.name = name_map.get(ln.part_id, "")

    return WorkOrderMaterialsResponse(
        work_order_id=wo.work_order_id,
        code=wo.code,
        current_stage=wo.current_stage,
        lines=lines,
    )
