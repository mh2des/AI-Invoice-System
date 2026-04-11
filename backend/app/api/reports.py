import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.db.session import get_db
from app.models.invoice import Invoice
from app.services.excel_export import generate_invoice_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/invoices/{invoice_id}/generate-report")
async def generate_report(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate an Excel report for a processed invoice.

    Returns the Excel file directly as a download.
    Also attempts to store the file in R2 for future downloads.
    """
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items), selectinload(Invoice.supplier))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"Invoice must be in 'done' status to generate report (current: {invoice.status})",
        )

    # Build data dicts for the report
    invoice_data = {
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "payment_terms": invoice.payment_terms,
        "currency": invoice.currency,
        "subtotal": invoice.subtotal,
        "discount_total": invoice.discount_total,
        "grand_total": invoice.grand_total,
    }

    supplier_data = None
    if invoice.supplier:
        supplier_data = {
            "name": invoice.supplier.name,
            "address": invoice.supplier.address,
            "phone": invoice.supplier.phone,
            "bank_name": invoice.supplier.bank_name,
            "bank_account": invoice.supplier.bank_account,
        }

    items_data = []
    for item in sorted(invoice.items, key=lambda x: x.line_number or 0):
        items_data.append({
            "line_number": item.line_number,
            "extracted_name": item.extracted_name,
            "extracted_barcode": item.extracted_barcode,
            "extracted_qty": item.extracted_qty,
            "extracted_uom": item.extracted_uom,
            "extracted_unit_price": item.extracted_unit_price,
            "extracted_discount": item.extracted_discount,
            "extracted_total": item.extracted_total,
            "matched": item.matched,
            "match_confidence": item.match_confidence,
            "match_method": item.match_method,
        })

    # Generate the Excel file
    excel_bytes = generate_invoice_report(invoice_data, items_data, supplier_data)

    # Try to store in R2 for future downloads
    try:
        from app.services.storage import upload_file
        inv_num = invoice.invoice_number or f"invoice-{invoice_id}"
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in inv_num)
        filename = f"report-{safe_name}.xlsx"
        key = await upload_file(excel_bytes, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        invoice.excel_file_url = key
        await db.commit()
        logger.info("Report stored in R2: %s", key)
    except Exception as e:
        logger.warning("Could not store report in R2 (non-fatal): %s", e)

    # Return the file directly
    inv_display = invoice.invoice_number or f"invoice-{invoice_id}"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="report-{inv_display}.xlsx"',
        },
    )


@router.get("/invoices/{invoice_id}/download-report")
async def download_report(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Download a previously generated Excel report.

    If the report was stored in R2, downloads from there.
    Otherwise, regenerates the report on-the-fly.
    """
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # If we have a stored report in R2, try to fetch it
    if invoice.excel_file_url and not invoice.excel_file_url.startswith("local://"):
        try:
            from app.services.storage import download_file
            excel_bytes = await download_file(invoice.excel_file_url)
            inv_display = invoice.invoice_number or f"invoice-{invoice_id}"
            return Response(
                content=excel_bytes,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": f'attachment; filename="report-{inv_display}.xlsx"',
                },
            )
        except Exception as e:
            logger.warning("Could not download report from R2, regenerating: %s", e)

    # Fallback: regenerate the report
    return await generate_report(invoice_id, db)
