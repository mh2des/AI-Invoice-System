from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


# --- Invoice Item schemas ---

class InvoiceItemBase(BaseModel):
    line_number: int | None = None
    extracted_name: str | None = None
    extracted_barcode: str | None = None
    extracted_qty: Decimal | None = None
    extracted_uom: str | None = None
    extracted_unit_price: Decimal | None = None
    extracted_discount: Decimal | None = None
    extracted_total: Decimal | None = None


class InvoiceItemResponse(InvoiceItemBase):
    id: int
    invoice_id: int
    product_id: int | None = None
    matched: bool
    match_confidence: Decimal | None = None
    match_method: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceItemManualMatch(BaseModel):
    product_id: int


# --- Invoice schemas ---

class InvoiceBase(BaseModel):
    invoice_number: str | None = None
    supplier_id: int | None = None
    invoice_date: date | None = None
    payment_terms: str | None = None
    currency: str = "MYR"


class InvoiceResponse(InvoiceBase):
    id: int
    uploaded_by: str | None = None
    image_urls: list[str] | None = None
    status: str
    subtotal: Decimal | None = None
    discount_total: Decimal | None = None
    grand_total: Decimal | None = None
    excel_file_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InvoiceDetailResponse(InvoiceResponse):
    items: list[InvoiceItemResponse] = []
    supplier_name: str | None = None


class DashboardStats(BaseModel):
    total_invoices: int
    total_products: int
    total_suppliers: int
    invoices_done: int
    invoices_pending: int
    invoices_failed: int
    match_rate: float


# --- Matching schemas ---

class MatchCandidate(BaseModel):
    product_id: int
    product_name: str
    confidence: float
    method: str


class MatchItemResult(BaseModel):
    item_id: int
    line_number: int | None = None
    extracted_name: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    matched: bool
    confidence: float | None = None
    method: str | None = None
    uom_mismatch: bool = False
    candidates: list[MatchCandidate] = []


class MatchSummaryResponse(BaseModel):
    total: int
    matched: int
    unmatched: int
    match_rate: float
    items: list[MatchItemResult] = []


class ProductSuggestion(BaseModel):
    product_id: int
    product_name: str
    barcode: str | None = None
    uom: str | None = None
    confidence: float
