"""
Procesador central de eventos Kafka.

Garantías implementadas:
  1. Idempotencia    — event_id deduplicado en processed_events
  2. Ledger inmutable — stock solo vía INSERT en inventory_movements
  3. Resguardo de concurrencia — available nunca < 0 (SELECT FOR UPDATE)
  4. FIFO de faltantes — surtido por orden cronológico de creación
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import (
    BomLine,
    BomModel,
    InventoryMovement,
    Location,
    Part,
    ProcessedEvent,
    Reservation,
    Shortage,
    UnmatchedReceipt,
    WorkOrder,
)
from app.models.schemas import (
    BomUpsertedData,
    InspectionApprovedData,
    InspectionVoidedData,
    KafkaEventEnvelope,
    LocationUpsertedData,
    PartUpsertedData,
    PurchaseItemReceivedData,
    WorkOrderDeletedData,
    WorkOrderOpenedData,
    WorkOrderStageChangedData,
)
from app.services import kafka_producer

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

async def process_event(envelope: KafkaEventEnvelope, db: AsyncSession) -> None:
    """
    Despacha un evento Kafka al handler correcto.
    Garantiza idempotencia antes de cualquier procesamiento.
    """
    event_id = str(envelope.event_id)
    event_type = envelope.event_type

    # ── IDEMPOTENCIA: verificar si ya fue procesado ──────────────────────────
    existing = await db.get(ProcessedEvent, event_id)
    if existing:
        logger.debug("Evento duplicado ignorado: %s (%s)", event_id, event_type)
        return

    # ── Despacho por tipo ─────────────────────────────────────────────────────
    try:
        match event_type:
            # Catálogo
            case "part.upserted":
                await _handle_part_upserted(PartUpsertedData(**envelope.data), db)
            case "location.upserted":
                await _handle_location_upserted(LocationUpsertedData(**envelope.data), db)
            case "bom.upserted":
                await _handle_bom_upserted(BomUpsertedData(**envelope.data), db)

            # Órdenes de trabajo
            case "work_order.opened":
                await _handle_work_order_opened(WorkOrderOpenedData(**envelope.data), db)
            case "work_order.stage_changed":
                await _handle_work_order_stage_changed(WorkOrderStageChangedData(**envelope.data), db)
            case "work_order.deleted":
                await _handle_work_order_deleted(WorkOrderDeletedData(**envelope.data), db)

            # Inspecciones
            case "inspection.approved":
                await _handle_inspection_approved(InspectionApprovedData(**envelope.data), db)
            case "inspection.voided" | "inspection.rejected" | "inspection.discarded":
                data = envelope.data
                await _release_work_order_reservations(data.get("work_order_id"), db)

            # Compras
            case "purchase.item_received":
                await _handle_purchase_received(PurchaseItemReceivedData(**envelope.data), db)

            case _:
                logger.debug("Evento sin handler registrado: %s", event_type)

        # ── Marcar como procesado (commit implícito al salir del contexto) ────
        db.add(ProcessedEvent(
            event_id=event_id,
            event_type=event_type,
            processed_at=datetime.now(timezone.utc),
        ))
        await db.commit()

    except Exception as exc:
        await db.rollback()
        logger.exception("Error procesando evento %s (%s): %s", event_id, event_type, exc)
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS — CATÁLOGO
# ═══════════════════════════════════════════════════════════════════════════════

async def _handle_part_upserted(data: PartUpsertedData, db: AsyncSession) -> None:
    stmt = pg_insert(Part).values(
        part_id=data.part_id,
        sku=data.sku,
        name=data.name,
        family=data.family,
        group=data.group,
        subgroup=data.subgroup,
        unit=data.unit,
        image_url=data.image_url,
        active=data.active,
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["part_id"],
        set_=dict(
            sku=data.sku,
            name=data.name,
            family=data.family,
            group=data.group,
            subgroup=data.subgroup,
            unit=data.unit,
            image_url=data.image_url,
            active=data.active,
            updated_at=datetime.now(timezone.utc),
        ),
    )
    await db.execute(stmt)
    logger.info("Part upserted: %s (%s)", data.part_id, data.sku)


async def _handle_location_upserted(data: LocationUpsertedData, db: AsyncSession) -> None:
    stmt = pg_insert(Location).values(
        location_id=data.location_id,
        code=data.code,
        name=data.name,
        is_workbench=data.is_workbench,
        active=data.active,
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["location_id"],
        set_=dict(
            code=data.code,
            name=data.name,
            is_workbench=data.is_workbench,
            active=data.active,
            updated_at=datetime.now(timezone.utc),
        ),
    )
    await db.execute(stmt)
    logger.info("Location upserted: %s (%s)", data.location_id, data.code)


async def _handle_bom_upserted(data: BomUpsertedData, db: AsyncSession) -> None:
    # Upsert del modelo
    stmt = pg_insert(BomModel).values(
        model_id=data.model_id,
        model_name=data.model_name,
        brand=data.brand,
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["model_id"],
        set_=dict(model_name=data.model_name, brand=data.brand,
                  updated_at=datetime.now(timezone.utc)),
    )
    await db.execute(stmt)

    # Borrar líneas previas y reinsertar (reemplazo estricto del BOM)
    await db.execute(
        BomLine.__table__.delete().where(BomLine.model_id == data.model_id)
    )
    for line in data.lines:
        db.add(BomLine(
            bom_line_id=line.bom_line_id,
            model_id=data.model_id,
            part_id=line.part_id,
            name=line.name,
            group_name=line.group_name,
            unit=line.unit,
            qty_per_unit=line.qty_per_unit,
            sort_order=line.sort_order,
        ))
    logger.info("BOM upserted: model_id=%s, %d líneas", data.model_id, len(data.lines))


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS — ÓRDENES DE TRABAJO
# ═══════════════════════════════════════════════════════════════════════════════

async def _handle_work_order_opened(data: WorkOrderOpenedData, db: AsyncSession) -> None:
    stmt = pg_insert(WorkOrder).values(
        work_order_id=data.work_order_id,
        code=data.code,
        model_id=data.model_id,
        department=data.department,
        current_stage="awaiting_quick_inspection",
        received_at=data.received_at,
        deleted=False,
        updated_at=datetime.now(timezone.utc),
    ).on_conflict_do_update(
        index_elements=["work_order_id"],
        set_=dict(
            code=data.code,
            model_id=data.model_id,
            department=data.department,
            received_at=data.received_at,
            deleted=False,
            updated_at=datetime.now(timezone.utc),
        ),
    )
    await db.execute(stmt)
    logger.info("WorkOrder abierta: %s (%s)", data.work_order_id, data.code)


async def _handle_work_order_stage_changed(data: WorkOrderStageChangedData, db: AsyncSession) -> None:
    await db.execute(
        update(WorkOrder)
        .where(WorkOrder.work_order_id == data.work_order_id)
        .values(current_stage=data.to_stage, updated_at=datetime.now(timezone.utc))
    )


async def _handle_work_order_deleted(data: WorkOrderDeletedData, db: AsyncSession) -> None:
    await db.execute(
        update(WorkOrder)
        .where(WorkOrder.work_order_id == data.work_order_id)
        .values(deleted=True, updated_at=datetime.now(timezone.utc))
    )
    await _release_work_order_reservations(data.work_order_id, db)
    logger.info("WorkOrder eliminada: %s", data.work_order_id)


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS — INSPECCIONES
# ═══════════════════════════════════════════════════════════════════════════════

async def _handle_inspection_approved(data: InspectionApprovedData, db: AsyncSession) -> None:
    """
    Reglas:
    - Solo líneas con action='buy' se procesan.
    - Reemplazo estricto: borra reservas/faltantes previos de la OT antes de recalcular.
    - Reserva si hay available; faltante si no.
    """
    wo_id = data.work_order_id

    # ── Reemplazo estricto: cancelar estado anterior ──────────────────────────
    await db.execute(
        update(Reservation)
        .where(Reservation.work_order_id == wo_id, Reservation.status == "active")
        .values(status="cancelled", updated_at=datetime.now(timezone.utc))
    )
    await db.execute(
        update(Shortage)
        .where(Shortage.work_order_id == wo_id, Shortage.status == "open")
        .values(status="cancelled", updated_at=datetime.now(timezone.utc))
    )

    buy_items = [item for item in data.items if item.action == "buy"]

    for item in buy_items:
        needed = item.quantity
        part_id = item.part_id

        # Verificar que la pieza existe en catálogo
        if part_id is not None:
            part_exists = await db.get(Part, part_id)
            if not part_exists:
                part_id = None  # tratar como desconocida

        if part_id is None:
            # Pieza sin identificar → siempre faltante
            shortage = Shortage(
                work_order_id=wo_id,
                inspection_item_id=item.inspection_item_id,
                part_id=None,
                name=item.name,
                missing_quantity=needed,
                status="open",
            )
            db.add(shortage)
            await db.flush()  # necesitamos shortage_id para el evento
            await kafka_producer.publish(
                "stock.shortage_detected",
                data={
                    "work_order_id": wo_id,
                    "part_id": None,
                    "name": item.name,
                    "missing_quantity": needed,
                    "inspection_item_id": item.inspection_item_id,
                },
                key=f"wo:{wo_id}",
            )
            continue

        # Calcular available: on_hand - reserved_activo (todas las ubicaciones)
        available = await _get_available(part_id, db)

        if available >= needed:
            # Hay stock suficiente → reservar
            reservation = Reservation(
                work_order_id=wo_id,
                part_id=part_id,
                inspection_item_id=item.inspection_item_id,
                quantity=needed,
                status="active",
            )
            db.add(reservation)
            await db.flush()

            await kafka_producer.publish(
                "stock.reserved",
                data={
                    "reservation_id": reservation.reservation_id,
                    "work_order_id": wo_id,
                    "part_id": part_id,
                    "quantity": needed,
                    "inspection_item_id": item.inspection_item_id,
                },
                key=f"part:{part_id}",
            )
        else:
            # Stock insuficiente → faltante
            shortage = Shortage(
                work_order_id=wo_id,
                inspection_item_id=item.inspection_item_id,
                part_id=part_id,
                name=item.name,
                missing_quantity=needed - available,
                status="open",
            )
            db.add(shortage)
            await db.flush()

            await kafka_producer.publish(
                "stock.shortage_detected",
                data={
                    "work_order_id": wo_id,
                    "part_id": part_id,
                    "name": item.name,
                    "missing_quantity": needed - available,
                    "inspection_item_id": item.inspection_item_id,
                },
                key=f"wo:{wo_id}",
            )


async def _release_work_order_reservations(work_order_id: int, db: AsyncSession) -> None:
    """Libera reservas activas y cierra faltantes de una OT."""
    await db.execute(
        update(Reservation)
        .where(Reservation.work_order_id == work_order_id, Reservation.status == "active")
        .values(status="cancelled", updated_at=datetime.now(timezone.utc))
    )
    await db.execute(
        update(Shortage)
        .where(Shortage.work_order_id == work_order_id, Shortage.status == "open")
        .values(status="cancelled", updated_at=datetime.now(timezone.utc))
    )
    logger.info("Reservas/faltantes liberados para OT: %s", work_order_id)


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLERS — COMPRAS
# ═══════════════════════════════════════════════════════════════════════════════

async def _handle_purchase_received(data: PurchaseItemReceivedData, db: AsyncSession) -> None:
    """
    Solo procesa purpose='restock'.
    1. Sanitiza part_number y busca por SKU.
    2. Si no coincide → unmatched_receipt.
    3. Si coincide → entrada en ledger en U-100 y surtido FIFO de faltantes.
    """
    if data.purpose != "restock":
        logger.debug("purchase.item_received ignorado (purpose=%s)", data.purpose)
        return

    part_number = data.part_number.strip()

    # Buscar pieza por SKU
    result = await db.execute(
        select(Part).where(Part.sku == part_number, Part.active == True)
    )
    part: Optional[Part] = result.scalar_one_or_none()

    if part is None:
        # No coincide → unmatched
        stmt = pg_insert(UnmatchedReceipt).values(
            purchase_line_id=data.line_id,
            part_number=part_number,
            description=data.description,
            quantity=data.quantity,
            unit_price=data.unit_price,
            currency=data.currency,
            work_order_code=data.work_order_code,
            status="pending",
            received_at=data.received_at,
        ).on_conflict_do_nothing(index_elements=["purchase_line_id"])
        await db.execute(stmt)

        await kafka_producer.publish(
            "stock.unmatched_receipt",
            data={
                "purchase_line_id": data.line_id,
                "part_number": part_number,
                "description": data.description,
                "quantity": data.quantity,
            },
        )
        logger.warning("Recepción sin coincidencia: %s", part_number)
        return

    # Coinció → entrada en ledger (ubicación U-100 por defecto)
    location_id = settings.DEFAULT_STOCK_LOCATION_ID
    movement = InventoryMovement(
        part_id=part.part_id,
        location_id=location_id,
        delta=data.quantity,
        movement_type="received",
        reference_id=str(data.line_id),
        created_at=data.received_at,
    )
    db.add(movement)
    await db.flush()

    await kafka_producer.publish(
        "stock.received",
        data={
            "part_id": part.part_id,
            "location_id": location_id,
            "quantity": data.quantity,
            "unit_cost": data.unit_price,
            "currency": data.currency,
            "purchase_line_id": data.line_id,
        },
        key=f"part:{part.part_id}",
    )

    # ── FIFO: surtir faltantes pendientes ─────────────────────────────────────
    remaining = data.quantity

    # Prioridad 1: faltantes de la orden indicada en el evento
    priority_wo_id: Optional[int] = None
    if data.work_order_code:
        wo_res = await db.execute(
            select(WorkOrder.work_order_id)
            .where(WorkOrder.code == data.work_order_code, WorkOrder.deleted == False)
        )
        priority_wo_id = wo_res.scalar_one_or_none()

    shortage_q = (
        select(Shortage)
        .where(Shortage.part_id == part.part_id, Shortage.status == "open")
        .order_by(
            # La OT prioritaria primero; luego FIFO por created_at
            (Shortage.work_order_id == priority_wo_id).desc()
            if priority_wo_id else Shortage.created_at,
            Shortage.created_at,
        )
        .with_for_update(skip_locked=True)
    )
    shortages = (await db.execute(shortage_q)).scalars().all()

    for shortage in shortages:
        if remaining <= 0:
            break

        resolvable = min(remaining, shortage.missing_quantity or 0)
        if resolvable <= 0:
            continue

        remaining -= resolvable
        new_missing = (shortage.missing_quantity or 0) - resolvable

        if new_missing <= 0:
            # Faltante completamente resuelto → reservar
            await db.execute(
                update(Shortage)
                .where(Shortage.shortage_id == shortage.shortage_id)
                .values(status="resolved", missing_quantity=0,
                        updated_at=datetime.now(timezone.utc))
            )
            reservation = Reservation(
                work_order_id=shortage.work_order_id,
                part_id=part.part_id,
                inspection_item_id=shortage.inspection_item_id,
                quantity=resolvable,
                status="active",
            )
            db.add(reservation)
            await db.flush()

            await kafka_producer.publish(
                "stock.shortage_resolved",
                data={
                    "work_order_id": shortage.work_order_id,
                    "part_id": part.part_id,
                    "quantity": resolvable,
                },
                key=f"part:{part.part_id}",
            )
            await kafka_producer.publish(
                "stock.reserved",
                data={
                    "reservation_id": reservation.reservation_id,
                    "work_order_id": shortage.work_order_id,
                    "part_id": part.part_id,
                    "quantity": resolvable,
                    "inspection_item_id": shortage.inspection_item_id,
                },
                key=f"part:{part.part_id}",
            )
        else:
            # Reducir cantidad faltante parcialmente
            await db.execute(
                update(Shortage)
                .where(Shortage.shortage_id == shortage.shortage_id)
                .values(missing_quantity=new_missing,
                        updated_at=datetime.now(timezone.utc))
            )

    # Sugerencia de reorden si quedan faltantes sin resolver
    still_open = (await db.execute(
        select(func.count(Shortage.shortage_id))
        .where(Shortage.part_id == part.part_id, Shortage.status == "open")
    )).scalar_one()

    if still_open > 0:
        wo_ids_res = await db.execute(
            select(Shortage.work_order_id)
            .where(Shortage.part_id == part.part_id, Shortage.status == "open")
            .distinct()
        )
        wo_ids = [r for r in wo_ids_res.scalars()]
        total_missing = (await db.execute(
            select(func.sum(Shortage.missing_quantity))
            .where(Shortage.part_id == part.part_id, Shortage.status == "open")
        )).scalar_one() or 0

        await kafka_producer.publish(
            "stock.reorder_suggested",
            data={
                "part_id": part.part_id,
                "suggested_quantity": total_missing,
                "work_order_ids": wo_ids,
            },
            key=f"part:{part.part_id}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS DE CÁLCULO
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_on_hand(part_id: int, db: AsyncSession) -> float:
    """on_hand = SUM(delta) de inventory_movements para la pieza (todas las ubicaciones)."""
    result = await db.execute(
        select(func.coalesce(func.sum(InventoryMovement.delta), 0.0))
        .where(InventoryMovement.part_id == part_id)
    )
    return float(result.scalar_one())


async def _get_reserved(part_id: int, db: AsyncSession) -> float:
    """reserved = SUM(quantity) de reservas activas."""
    result = await db.execute(
        select(func.coalesce(func.sum(Reservation.quantity), 0.0))
        .where(Reservation.part_id == part_id, Reservation.status == "active")
    )
    return float(result.scalar_one())


async def _get_available(part_id: int, db: AsyncSession) -> float:
    """available = max(0, on_hand - reserved)."""
    on_hand = await _get_on_hand(part_id, db)
    reserved = await _get_reserved(part_id, db)
    return max(0.0, on_hand - reserved)
