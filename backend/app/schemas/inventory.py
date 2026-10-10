from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field


# ── Availability ─────────────────────────────────────────────────────────────
class LocationAvailability(BaseModel):
    location_id: int
    code: Optional[str] = None
    on_hand: int
    reserved: int = 0
    available: int


class AvailabilityResponse(BaseModel):
    part_id: int
    on_hand: int
    reserved: int
    available: int
    locations: List[LocationAvailability]


# ── Movement & Ledger ─────────────────────────────────────────────────────────
class MovementResponse(BaseModel):
    movement_id: Union[int, str]
    type: str
    part_id: int
    location_id: int
    quantity: int
    occurred_at: datetime
    reference: Optional[str] = None


class LedgerEntry(MovementResponse):
    balance: int


class LedgerResponse(BaseModel):
    part_id: int
    entries: List[LedgerEntry]


# ── Work Order Materials ─────────────────────────────────────────────────────
class MaterialLine(BaseModel):
    inspection_item_id: int
    bom_line_id: int
    part_id: Optional[int] = None
    name: str
    required: Optional[int] = None
    reserved: int = 0
    issued: int = 0
    missing: Optional[int] = None


class WorkOrderMaterialsResponse(BaseModel):
    work_order_id: int
    code: str
    lines: List[MaterialLine]


# ── Shortages ────────────────────────────────────────────────────────────────
class ShortageItem(BaseModel):
    work_order_id: int
    work_order_code: str
    part_id: Optional[int] = None
    name: str
    missing_quantity: Optional[int] = None
    inspection_item_id: int
    opened_at: Optional[datetime] = None


class ShortagesListResponse(BaseModel):
    items: List[ShortageItem]


# ── Reorder Suggestions ──────────────────────────────────────────────────────
class ReorderSuggestionItem(BaseModel):
    part_id: int
    sku: Optional[str] = None
    name: str
    suggested_quantity: int
    work_order_ids: List[int]


class ReorderSuggestionsResponse(BaseModel):
    items: List[ReorderSuggestionItem]


# ── Unmatched Receipts ───────────────────────────────────────────────────────
class UnmatchedReceiptItem(BaseModel):
    id: Union[int, str]
    purchase_line_id: int
    part_number: str
    description: str
    quantity: int
    unit_price: Optional[str] = None
    currency: Optional[str] = None
    received_at: datetime
    work_order_code: Optional[str] = None


class UnmatchedReceiptsResponse(BaseModel):
    items: List[UnmatchedReceiptItem]


class ResolveReceiptRequest(BaseModel):
    part_id: int
    location_id: Optional[int] = None


# ── Operations Requests ──────────────────────────────────────────────────────
class IssueRequest(BaseModel):
    work_order_code: str
    part_id: int
    location_id: int
    quantity: int = Field(..., ge=1)
    issued_by: Union[int, str]


class TransferRequest(BaseModel):
    part_id: int
    from_location_id: int
    to_location_id: int
    quantity: int = Field(..., ge=1)


class CountLineItem(BaseModel):
    part_id: int
    counted_quantity: int = Field(..., ge=0)


class CountRequest(BaseModel):
    location_id: int
    reason: str = Field(..., min_length=1)
    lines: List[CountLineItem]


class AdjustmentItem(BaseModel):
    part_id: int
    delta: int


class CountResponse(BaseModel):
    adjustments: List[AdjustmentItem]


# ── Error ────────────────────────────────────────────────────────────────────
class ErrorResponse(BaseModel):
    detail: str