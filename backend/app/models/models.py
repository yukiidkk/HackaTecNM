from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    BigInteger,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ProcessedEvent(Base):
    """Control de idempotencia para eventos consumidos de Kafka/Redpanda."""
    __tablename__ = "processed_events"

    event_id = Column(String(64), primary_key=True)
    event_type = Column(String(64), nullable=False)
    topic = Column(String(64), nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Part(Base):
    """Catálogo de refacciones y servicios industriales."""
    __tablename__ = "parts"

    part_id = Column(Integer, primary_key=True)
    sku = Column(String(128), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    family = Column(String(64), nullable=True)
    group_name = Column(String(128), nullable=True)
    default_location_id = Column(Integer, nullable=True)
    unit = Column(String(32), default="piece")
    min_stock = Column(Integer, default=0)
    is_service = Column(Boolean, default=False)


class Location(Base):
    """Ubicaciones físicas del taller (mesas, estantes, recepción U-100)."""
    __tablename__ = "locations"

    location_id = Column(Integer, primary_key=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    is_workbench = Column(Boolean, default=False)


class BomLine(Base):
    """Líneas de lista de materiales (BOM) por modelo de equipo."""
    __tablename__ = "bom_lines"

    bom_line_id = Column(Integer, primary_key=True)
    model_id = Column(Integer, nullable=False, index=True)
    part_id = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=False)
    group_name = Column(String(128), nullable=True)
    qty_per_unit = Column(Integer, nullable=True)
    action = Column(String(32), nullable=True)


class WorkOrder(Base):
    """Órdenes de trabajo del taller (reparación de motores y husillos)."""
    __tablename__ = "work_orders"

    work_order_id = Column(Integer, primary_key=True)
    code = Column(String(64), nullable=False, unique=True, index=True)
    model_id = Column(Integer, nullable=True)
    stage = Column(String(64), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=True)


class InventoryMovement(Base):
    """Libro mayor inmutable (Kardex de movimientos de inventario)."""
    __tablename__ = "inventory_movements"

    movement_id = Column(BigInteger, primary_key=True, autoincrement=True)
    type = Column(String(32), nullable=False)
    part_id = Column(Integer, nullable=False, index=True)
    location_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    reference = Column(String(255), nullable=True)
    purchase_line_id = Column(Integer, nullable=True)
    work_order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Reservation(Base):
    """Reservas activas o cumplidas de refacciones por orden de trabajo."""
    __tablename__ = "reservations"

    reservation_id = Column(Integer, primary_key=True, autoincrement=True)
    work_order_id = Column(Integer, nullable=False, index=True)
    bom_line_id = Column(Integer, nullable=True, index=True)
    part_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    inspection_item_id = Column(Integer, nullable=True)
    status = Column(String(32), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Shortage(Base):
    """Faltantes abiertos o resueltos de material."""
    __tablename__ = "shortages"

    shortage_id = Column(Integer, primary_key=True, autoincrement=True)
    work_order_id = Column(Integer, nullable=False, index=True)
    work_order_code = Column(String(64), nullable=True, index=True)
    bom_line_id = Column(Integer, nullable=True)
    part_id = Column(Integer, nullable=True, index=True)
    name = Column(String(255), nullable=False)
    missing_quantity = Column(Integer, nullable=True)
    inspection_item_id = Column(Integer, nullable=True)
    status = Column(String(32), default="open", nullable=False)
    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)


class UnmatchedReceipt(Base):
    """Recepciones de compra pendientes de relacionar con el catálogo."""
    __tablename__ = "unmatched_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    purchase_line_id = Column(Integer, nullable=False, unique=True)
    part_number = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(8), nullable=True)
    work_order_code = Column(String(64), nullable=True)
    status = Column(String(32), default="pending", nullable=False)
    resolved_part_id = Column(Integer, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)