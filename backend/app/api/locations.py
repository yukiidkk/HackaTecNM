"""
Router: /locations

  GET /locations/stock-summary — resumen de stock por ubicación
  (endpoint adicional requerido por el frontend — WarehouseTab)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import InventoryMovement, Location, get_db
from app.models.schemas import LocationStockSummary

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get(
    "/stock-summary",
    response_model=list[LocationStockSummary],
    summary="Resumen de stock por ubicación física",
)
async def get_locations_stock_summary(
    db: AsyncSession = Depends(get_db),
) -> list[LocationStockSummary]:
    # Todas las ubicaciones activas
    locations = (await db.execute(
        select(Location).where(Location.active == True).order_by(Location.code)
    )).scalars().all()

    # Stock agregado por ubicación
    stock_rows = (await db.execute(
        select(
            InventoryMovement.location_id,
            func.count(InventoryMovement.part_id.distinct()).label("total_parts"),
            func.coalesce(func.sum(InventoryMovement.delta), 0.0).label("total_on_hand"),
        )
        .group_by(InventoryMovement.location_id)
    )).all()

    stock_map: dict[int, tuple[int, float]] = {
        r.location_id: (int(r.total_parts), float(r.total_on_hand))
        for r in stock_rows
    }

    return [
        LocationStockSummary(
            location_id=loc.location_id,
            location_code=loc.code,
            location_name=loc.name,
            is_workbench=loc.is_workbench,
            total_parts=stock_map.get(loc.location_id, (0, 0.0))[0],
            total_on_hand=max(0.0, stock_map.get(loc.location_id, (0, 0.0))[1]),
        )
        for loc in locations
    ]
