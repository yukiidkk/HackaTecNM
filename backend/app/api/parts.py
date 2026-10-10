"""
Router: /parts

  GET /parts/{part_id}/availability  — saldo por ubicación
  GET /parts/{part_id}/ledger        — libro mayor (kardex)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (
    InventoryMovement,
    Location,
    Part,
    Reservation,
    get_db,
)
from app.models.schemas import (
    LedgerEntryResponse,
    LocationStock,
    PartAvailabilityResponse,
)

router = APIRouter(prefix="/parts", tags=["parts"])


# ── GET /parts/{part_id}/availability ─────────────────────────────────────────

@router.get(
    "/{part_id}/availability",
    response_model=PartAvailabilityResponse,
    summary="Stock disponible por ubicación",
)
async def get_part_availability(
    part_id: int,
    db: AsyncSession = Depends(get_db),
) -> PartAvailabilityResponse:
    # Verificar que la pieza existe
    part = await db.get(Part, part_id)
    if not part:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pieza no encontrada")

    # on_hand por ubicación (SUM del ledger)
    on_hand_rows = (await db.execute(
        select(
            InventoryMovement.location_id,
            func.coalesce(func.sum(InventoryMovement.delta), 0.0).label("on_hand"),
        )
        .where(InventoryMovement.part_id == part_id)
        .group_by(InventoryMovement.location_id)
    )).all()

    # reserved total de la pieza (todas las ubicaciones — reservas no tienen location)
    total_reserved = float((await db.execute(
        select(func.coalesce(func.sum(Reservation.quantity), 0.0))
        .where(Reservation.part_id == part_id, Reservation.status == "active")
    )).scalar_one())

    # Información de ubicaciones
    location_ids = [r.location_id for r in on_hand_rows]
    locations_info: dict[int, Location] = {}
    if location_ids:
        loc_rows = (await db.execute(
            select(Location).where(Location.location_id.in_(location_ids))
        )).scalars().all()
        locations_info = {loc.location_id: loc for loc in loc_rows}

    # Distribuir reserved proporcionalmente entre ubicaciones
    total_on_hand = sum(float(r.on_hand) for r in on_hand_rows)
    location_stocks: list[LocationStock] = []

    for row in on_hand_rows:
        on_hand = max(0.0, float(row.on_hand))
        # Reservas se distribuyen proporcionalmente al on_hand de cada ubicación
        if total_on_hand > 0:
            loc_reserved = round(total_reserved * (on_hand / total_on_hand), 6)
        else:
            loc_reserved = 0.0

        available = max(0.0, on_hand - loc_reserved)
        loc = locations_info.get(row.location_id)

        location_stocks.append(LocationStock(
            location_id=row.location_id,
            location_code=loc.code if loc else str(row.location_id),
            location_name=loc.name if loc else "Desconocida",
            on_hand=on_hand,
            reserved=loc_reserved,
            available=available,
        ))

    return PartAvailabilityResponse(
        part_id=part.part_id,
        name=part.name,
        sku=part.sku,
        locations=location_stocks,
    )


# ── GET /parts/{part_id}/ledger ───────────────────────────────────────────────

@router.get(
    "/{part_id}/ledger",
    response_model=list[LedgerEntryResponse],
    summary="Libro mayor de movimientos (kardex)",
)
async def get_part_ledger(
    part_id: int,
    db: AsyncSession = Depends(get_db),
) -> list[LedgerEntryResponse]:
    part = await db.get(Part, part_id)
    if not part:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pieza no encontrada")

    # Todos los movimientos ordenados cronológicamente (asc) para calcular saldo acumulado
    movements = (await db.execute(
        select(InventoryMovement)
        .where(InventoryMovement.part_id == part_id)
        .order_by(InventoryMovement.created_at.asc(), InventoryMovement.movement_id.asc())
    )).scalars().all()

    # Calcular running_balance acumulado
    running = 0.0
    entries_asc: list[LedgerEntryResponse] = []
    for mov in movements:
        running += mov.delta
        entries_asc.append(LedgerEntryResponse(
            movement_id=mov.movement_id,
            part_id=mov.part_id,
            location_id=mov.location_id,
            delta=mov.delta,
            movement_type=mov.movement_type,
            reference_id=mov.reference_id,
            created_at=mov.created_at,
            running_balance=round(running, 6),
        ))

    # Retornar del más reciente al más antiguo (contrato del frontend)
    return list(reversed(entries_asc))
