from datetime import datetime
from pydantic import BaseModel


class SupplierBase(BaseModel):
    name: str
    address: str | None = None
    phone: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    notes: str | None = None


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None
    notes: str | None = None


class SupplierResponse(SupplierBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
