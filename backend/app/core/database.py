"""
Capa de acceso a datos con SQLAlchemy 2.0 async.

Tablas ORM definidas aquí reflejan el schema de Supabase/PostgreSQL.
Regla del Ledger: inventory_movements es append-only, nunca UPDATE/DELETE.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Engine y sesión ────────────────────────────────────────────────────────────

def _build_engine():
    return create_async_engine(
        settings.DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=(settings.APP_ENV == "development"),
    )


engine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncSession:  # type: ignore[return]
    """Dependency de FastAPI para inyectar sesión de BD."""
    async with AsyncSessionLocal() as session:
        yield session


# ── Base declarativa ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# TABLAS
# ═══════════════════════════════════════════════════════════════════════════════

class ProcessedEvent(Base):
    """Tabla de idempotencia. Guarda event_id ya procesados."""
    __tablename__ = "processed_events"

    event_id = Column(String(36), primary_key=True)
    event_type = Column(String(100), nullable=False)
    processed_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class Part(Base):
    """Catálogo de piezas."""
    __tablename__ = "parts"

    part_id = Column(Integer, primary_key=True)
    sku = Column(String(100), unique=True, nullable=True)
    name = Column(String(255), nullable=False)
    family = Column(String(100), nullable=True)
    group = Column(String(100), nullable=True)
    subgroup = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    image_url = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    movements = relationship("InventoryMovement", back_populates="part", lazy="noload")
    reservations = relationship("Reservation", back_populates="part", lazy="noload")


class Location(Base):
    """Ubicaciones físicas del almacén y bancas de trabajo."""
    __tablename__ = "locations"

    location_id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False)   # U-014, U-100
    name = Column(String(255), nullable=False)
    is_workbench = Column(Boolean, default=False, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class BomModel(Base):
    """Modelos de máquina (cabezales, motores)."""
    __tablename__ = "bom_models"

    model_id = Column(Integer, primary_key=True)
    model_name = Column(String(255), nullable=False)
    brand = Column(String(100), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    lines = relationship("BomLine", back_populates="model", cascade="all, delete-orphan", lazy="noload")


class BomLine(Base):
    """Líneas de lista de materiales."""
    __tablename__ = "bom_lines"

    bom_line_id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("bom_models.model_id", ondelete="CASCADE"), nullable=False)
    part_id = Column(Integer, ForeignKey("parts.part_id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    group_name = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    qty_per_unit = Column(Float, default=1.0, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    model = relationship("BomModel", back_populates="lines", lazy="noload")


class WorkOrder(Base):
    """Órdenes de trabajo."""
    __tablename__ = "work_orders"

    work_order_id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)
    model_id = Column(Integer, ForeignKey("bom_models.model_id", ondelete="SET NULL"), nullable=True)
    department = Column(String(100), nullable=True)
    current_stage = Column(String(100), default="awaiting_quick_inspection", nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    reservations = relationship("Reservation", back_populates="work_order", lazy="noload")
    shortages = relationship("Shortage", back_populates="work_order", lazy="noload")


class InventoryMovement(Base):
    """
    Libro mayor INMUTABLE — nunca UPDATE ni DELETE.
    on_hand por (part_id, location_id) = SUM(delta) WHERE esas columnas.
    """
    __tablename__ = "inventory_movements"

    movement_id = Column(BigInteger, primary_key=True, autoincrement=True)
    part_id = Column(Integer, ForeignKey("parts.part_id", ondelete="RESTRICT"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.location_id", ondelete="RESTRICT"), nullable=False)
    delta = Column(Float, nullable=False)           # positivo=entrada, negativo=salida
    movement_type = Column(String(50), nullable=False)  # received/issued/transferred/adjusted/reserved_release
    reference_id = Column(String(100), nullable=True)   # work_order_code, purchase_line_id, etc.
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    part = relationship("Part", back_populates="movements", lazy="noload")

    __table_args__ = (
        Index("ix_inv_mov_part_location", "part_id", "location_id"),
        Index("ix_inv_mov_created_at", "created_at"),
    )


class Reservation(Base):
    """Reservas de stock para órdenes de trabajo."""
    __tablename__ = "reservations"

    reservation_id = Column(BigInteger, primary_key=True, autoincrement=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.work_order_id", ondelete="CASCADE"), nullable=False)
    part_id = Column(Integer, ForeignKey("parts.part_id", ondelete="RESTRICT"), nullable=False)
    inspection_item_id = Column(Integer, nullable=True)
    quantity = Column(Float, nullable=False)
    status = Column(String(20), default="active", nullable=False)  # active/fulfilled/cancelled
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    work_order = relationship("WorkOrder", back_populates="reservations", lazy="noload")
    part = relationship("Part", back_populates="reservations", lazy="noload")

    __table_args__ = (
        Index("ix_reservation_wo_part", "work_order_id", "part_id"),
    )


class Shortage(Base):
    """Faltantes detectados durante procesamiento de inspecciones."""
    __tablename__ = "shortages"

    shortage_id = Column(BigInteger, primary_key=True, autoincrement=True)
    work_order_id = Column(Integer, ForeignKey("work_orders.work_order_id", ondelete="CASCADE"), nullable=False)
    inspection_item_id = Column(Integer, nullable=True)
    part_id = Column(Integer, ForeignKey("parts.part_id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    missing_quantity = Column(Float, nullable=True)
    status = Column(String(20), default="open", nullable=False)  # open/resolved/cancelled
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    work_order = relationship("WorkOrder", back_populates="shortages", lazy="noload")

    __table_args__ = (
        Index("ix_shortage_wo_status", "work_order_id", "status"),
    )


class UnmatchedReceipt(Base):
    """Recepciones de compra que no coincidieron con el catálogo."""
    __tablename__ = "unmatched_receipts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    purchase_line_id = Column(Integer, unique=True, nullable=False)
    part_number = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    quantity = Column(Float, nullable=False)
    unit_price = Column(Float, nullable=True)
    currency = Column(String(10), default="MXN", nullable=True)
    work_order_code = Column(String(50), nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending/resolved/ignored
    received_at = Column(DateTime(timezone=True), nullable=False)
    resolved_part_id = Column(Integer, ForeignKey("parts.part_id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def create_all_tables() -> None:
    """Crea todas las tablas si no existen (solo para dev/testing sin Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Tablas verificadas/creadas correctamente.")
