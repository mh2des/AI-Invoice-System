from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.product import Product
from app.models.supplier import Supplier
from app.schemas.invoice import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    # Total counts
    total_invoices = (await db.execute(select(func.count(Invoice.id)))).scalar() or 0
    total_products = (await db.execute(select(func.count(Product.id)))).scalar() or 0
    total_suppliers = (await db.execute(select(func.count(Supplier.id)))).scalar() or 0

    # Invoice status counts
    invoices_done = (
        await db.execute(
            select(func.count(Invoice.id)).where(Invoice.status == "done")
        )
    ).scalar() or 0

    invoices_pending = (
        await db.execute(
            select(func.count(Invoice.id)).where(
                Invoice.status.in_(["pending", "processing"])
            )
        )
    ).scalar() or 0

    invoices_failed = (
        await db.execute(
            select(func.count(Invoice.id)).where(Invoice.status == "failed")
        )
    ).scalar() or 0

    # Match rate
    total_items = (
        await db.execute(select(func.count(InvoiceItem.id)))
    ).scalar() or 0

    matched_items = (
        await db.execute(
            select(func.count(InvoiceItem.id)).where(InvoiceItem.matched == True)  # noqa: E712
        )
    ).scalar() or 0

    match_rate = (matched_items / total_items * 100) if total_items > 0 else 0.0

    return DashboardStats(
        total_invoices=total_invoices,
        total_products=total_products,
        total_suppliers=total_suppliers,
        invoices_done=invoices_done,
        invoices_pending=invoices_pending,
        invoices_failed=invoices_failed,
        match_rate=round(match_rate, 1),
    )
