from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("products.id"), nullable=True
    )
    line_number: Mapped[int | None] = mapped_column(Integer)
    extracted_name: Mapped[str | None] = mapped_column(String(500))
    extracted_barcode: Mapped[str | None] = mapped_column(String(50))
    extracted_qty: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    extracted_uom: Mapped[str | None] = mapped_column(String(20))
    extracted_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    extracted_discount: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    extracted_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    match_method: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    invoice: Mapped["Invoice"] = relationship(back_populates="items")  # noqa: F821
    product: Mapped["Product | None"] = relationship()  # noqa: F821

    __table_args__ = (
        Index("idx_invoice_items_invoice", "invoice_id"),
        Index("idx_invoice_items_product", "product_id"),
    )
