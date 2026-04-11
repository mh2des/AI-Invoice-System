from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class ProductBase(BaseModel):
    barcode: str
    description: str
    stock_id: str | None = None
    uom: str = "PCS"
    cost: Decimal = Decimal("0")
    price: Decimal = Decimal("0")
    brand: str | None = None
    group_name: str | None = None
    category: str | None = None
    balance_qty: Decimal = Decimal("0")
    tax_code: str | None = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    barcode: str | None = None
    description: str | None = None
    stock_id: str | None = None
    uom: str | None = None
    cost: Decimal | None = None
    price: Decimal | None = None
    brand: str | None = None
    group_name: str | None = None
    category: str | None = None
    balance_qty: Decimal | None = None
    tax_code: str | None = None
    is_active: bool | None = None


class ProductResponse(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductImportResult(BaseModel):
    inserted: int
    updated: int
    skipped: int
    errors: list[str]
