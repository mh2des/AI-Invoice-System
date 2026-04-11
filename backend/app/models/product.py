from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[str | None] = mapped_column(String(50))
    barcode: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    uom: Mapped[str] = mapped_column(String(20), default="PCS")
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    brand: Mapped[str | None] = mapped_column(String(100))
    group_name: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(100))
    balance_qty: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    tax_code: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_products_description", "description"),
        Index("idx_products_group", "group_name"),
    )
