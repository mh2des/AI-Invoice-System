from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    supplier_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("suppliers.id"), nullable=True
    )
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    image_urls: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
    )
    invoice_date: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(10), default="MYR")
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    grand_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    raw_extraction: Mapped[dict | None] = mapped_column(JSONB)
    excel_file_url: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)
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
        CheckConstraint(
            "status IN ('pending', 'processing', 'done', 'failed')",
            name="ck_invoices_status",
        ),
    )

    # Relationships
    supplier: Mapped["Supplier"] = relationship(back_populates="invoices")  # noqa: F821
    items: Mapped[list["InvoiceItem"]] = relationship(  # noqa: F821
        back_populates="invoice", cascade="all, delete-orphan"
    )
