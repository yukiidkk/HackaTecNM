"""
Schemas Pydantic para:
  - Sobre de eventos Kafka (entrada y salida)
  - Payloads de cada event_type consumido
  - Respuestas de la API REST (contrato con el frontend)
  - Request bodies de los endpoints de escritura
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SOBRE GENÉRICO DE EVENTO KAFKA
# ═══════════════════════════════════════════════════════════════════════════════

class KafkaEventEnvelope(BaseModel):
    event_id: UUID
    event_type: str
    event_version: int = 1
    occurred_at: datetime
    source: str
    key: str
    data: dict[str, Any]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. PAYLOADS DE EVENTOS DE ENTRADA
# ═══════════════════════════════════════════════════════════════════════════════

# ── shop.catalog ──────────────────────────────────────────────────────────────

class PartUpsertedData(BaseModel):
    part_id: int
    sku: str
    name: str
    family: Optional[str] = None
    group: Optional[str] = None
    subgroup: Optional[str] = None
    unit: Optional[str] = None
    image_url: Optional[str] = None
    active: bool = True


class LocationUpsertedData(BaseModel):
    location_id: int
    code: str                    # ej. U-014, U-100
    name: str
    is_workbench: bool = False
    active: bool = True


class BomLine(BaseModel):
    bom_line_id: int
    part_id: Optional[int] = None
    name: str
    group_name: Optional[str] = None
    unit: Optional[str] = None
    qty_per_unit: float = 1.0
    sort_order: int = 0


class BomUpsertedData(BaseModel):
    model_id: int
    model_name: str
    brand: Optional[str] = None
    lines: list[BomLine] = Field(default_factory=list)


# ── shop.work_orders ──────────────────────────────────────────────────────────

class WorkOrderOpenedData(BaseModel):
    work_order_id: int
    code: str
    model_id: Optional[int] = None
    department: Optional[str] = None
    received_at: datetime


class WorkOrderStageChangedData(BaseModel):
    work_order_id: int
    from_stage: str
    to_stage: str


class WorkOrderDeletedData(BaseModel):
    work_order_id: int
    code: str


# ── shop.inspections ─────────────────────────────────────────────────────────

class InspectionItem(BaseModel):
    inspection_item_id: int
    bom_line_id: Optional[int] = None
    part_id: Optional[int] = None
    name: str
    group_name: Optional[str] = None
    condition: Literal["ok", "damaged", "missing"]
    action: Optional[Literal["buy", "repair"]] = None
    quantity: float = 1.0
    note: Optional[str] = None


class InspectionApprovedData(BaseModel):
    inspection_id: int
    work_order_id: int
    kind: str
    items: list[InspectionItem] = Field(default_factory=list)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class InspectionVoidedData(BaseModel):
    inspection_id: int
    work_order_id: int


# ── shop.purchasing ───────────────────────────────────────────────────────────

class PurchaseItemReceivedData(BaseModel):
    purchase_request_id: int
    request_number: str
    line_id: int
    part_number: str
    description: Optional[str] = None
    quantity: float
    unit_price: Optional[float] = None
    currency: Optional[str] = "MXN"
    purpose: Literal["restock", "customer_order"]
    received_at: datetime
    work_order_code: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. RESPUESTAS DE LA API REST  (coinciden con las interfaces TypeScript del frontend)
# ═══════════════════════════════════════════════════════════════════════════════

# ── GET /parts/{part_id}/availability ─────────────────────────────────────────

class LocationStock(BaseModel):
    location_id: int
    location_code: str
    location_name: str
    on_hand: float
    reserved: float
    available: float              # max(0, on_hand - reserved)


class PartAvailabilityResponse(BaseModel):
    part_id: int
    name: str
    sku: Optional[str] = None
    locations: list[LocationStock] = Field(default_factory=list)


# ── GET /parts/{part_id}/ledger ───────────────────────────────────────────────

class LedgerEntryResponse(BaseModel):
    movement_id: int
    part_id: int
    location_id: int
    delta: float
    movement_type: str
    reference_id: Optional[str] = None
    created_at: datetime
    running_balance: float


# ── GET /work-orders/{code}/materials ─────────────────────────────────────────

class WorkOrderMaterialLine(BaseModel):
    inspection_item_id: int
    bom_line_id: Optional[int] = None
    part_id: Optional[int] = None
    name: str
    reserved: float
    delivered: float
    shortage: Optional[float] = None


class WorkOrderMaterialsResponse(BaseModel):
    work_order_id: int
    code: str
    current_stage: str
    lines: list[WorkOrderMaterialLine] = Field(default_factory=list)


# ── GET /shortages ────────────────────────────────────────────────────────────

class ShortageResponse(BaseModel):
    shortage_id: int
    work_order_id: int
    part_id: Optional[int] = None
    name: str
    missing_quantity: Optional[float] = None
    status: Literal["open", "resolved", "cancelled"]
    created_at: datetime


# ── GET /reorder-suggestions ──────────────────────────────────────────────────

class ReorderSuggestionResponse(BaseModel):
    part_id: int
    name: str
    sku: Optional[str] = None
    suggested_quantity: float
    work_order_ids: list[int] = Field(default_factory=list)


# ── GET /unmatched-receipts ───────────────────────────────────────────────────

class UnmatchedReceiptResponse(BaseModel):
    id: int
    purchase_line_id: int
    part_number: str
    description: Optional[str] = None
    quantity: float
    work_order_code: Optional[str] = None
    status: Literal["pending", "resolved", "ignored"]
    received_at: datetime


# ── GET /locations/stock-summary (extra pedido por frontend) ──────────────────

class LocationStockSummary(BaseModel):
    location_id: int
    location_code: str
    location_name: str
    is_workbench: bool
    total_parts: int
    total_on_hand: float


# ═══════════════════════════════════════════════════════════════════════════════
# 4. REQUEST BODIES DE ENDPOINTS DE ESCRITURA
# ═══════════════════════════════════════════════════════════════════════════════

class ResolveUnmatchedReceiptRequest(BaseModel):
    part_id: int


class IssueRequest(BaseModel):
    work_order_code: str
    part_id: int
    location_id: int
    quantity: float = Field(gt=0)
    issued_by: str


class TransferRequest(BaseModel):
    part_id: int
    from_location_id: int
    to_location_id: int
    quantity: float = Field(gt=0)


class CountRequest(BaseModel):
    part_id: int
    location_id: int
    counted_quantity: float = Field(ge=0)
    reason: str


# ═══════════════════════════════════════════════════════════════════════════════
# 5. RESPUESTAS GENÉRICAS
# ═══════════════════════════════════════════════════════════════════════════════

class MovementCreatedResponse(BaseModel):
    movement_id: int


class ResolveOkResponse(BaseModel):
    ok: bool


class ErrorResponse(BaseModel):
    detail: str
