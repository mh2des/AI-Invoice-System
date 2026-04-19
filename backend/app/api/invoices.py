import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db, async_session_factory
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.supplier import Supplier
from app.schemas.invoice import (
    InvoiceDetailResponse,
    InvoiceItemResponse,
    InvoiceItemManualMatch,
    InvoiceResponse,
    MatchSummaryResponse,
    ProductSuggestion,
)
from app.services.extraction import extract_invoice_data
from app.services.storage import upload_file, get_presigned_url

logger = logging.getLogger(__name__)

# Allowed MIME types for invoice uploads
ALLOWED_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/tiff",
    "application/pdf",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB per file

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get("/", response_model=list[InvoiceResponse])
async def list_invoices(
    status: str | None = None,
    supplier_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    query = select(Invoice)

    if status:
        query = query.where(Invoice.status == status)
    if supplier_id:
        query = query.where(Invoice.supplier_id == supplier_id)

    query = query.order_by(Invoice.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice(invoice_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items), selectinload(Invoice.supplier))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    response = InvoiceDetailResponse.model_validate(invoice)
    if invoice.supplier:
        response.supplier_name = invoice.supplier.name
    return response


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(invoice_id: int, db: AsyncSession = Depends(get_db)):
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    await db.delete(invoice)
    await db.commit()


@router.post("/upload", response_model=InvoiceResponse, status_code=201)
async def upload_invoice(
    files: list[UploadFile] = File(..., description="Invoice images or PDF"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    """Upload invoice file(s) and trigger AI extraction in background.

    Accepts multiple images (for multi-page invoices) or a single PDF.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Validate files
    file_data: list[tuple[bytes, str, str]] = []  # (bytes, content_type, filename)
    for f in files:
        if f.content_type not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {f.content_type}. "
                f"Allowed: {', '.join(sorted(ALLOWED_TYPES))}",
            )
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {f.filename} exceeds maximum size of 20MB",
            )
        file_data.append((content, f.content_type, f.filename or "upload"))

    # Upload to R2 storage
    image_urls: list[str] = []
    for content, content_type, filename in file_data:
        try:
            key = await upload_file(content, filename, content_type)
            image_urls.append(key)
        except Exception as e:
            logger.warning(
                "R2 upload failed for %s, storing locally: %s", filename, e
            )
            # If R2 is not configured, we still proceed — images won't be stored
            # but extraction can still work from the bytes we already have
            image_urls.append(f"local://{filename}")

    # Create invoice record with status=pending
    invoice = Invoice(
        status="pending",
        image_urls=image_urls,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    # Trigger background extraction
    extraction_files = [(content, ctype) for content, ctype, _ in file_data]
    background_tasks.add_task(
        _process_extraction, invoice.id, extraction_files
    )

    return invoice


async def _process_extraction(
    invoice_id: int,
    files: list[tuple[bytes, str]],
) -> None:
    """Background task: run Gemini extraction and save results to DB."""
    async with async_session_factory() as db:
        try:
            # Update status to processing
            invoice = await db.get(Invoice, invoice_id)
            if not invoice:
                logger.error("Invoice %d not found for extraction", invoice_id)
                return

            invoice.status = "processing"
            invoice.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # Run Gemini extraction
            result = await extract_invoice_data(files)

            # Update invoice fields from extraction
            invoice.invoice_number = result.get("invoice_number")
            invoice.invoice_date = result.get("invoice_date")
            invoice.payment_terms = result.get("payment_terms")
            invoice.currency = result.get("currency", "MYR")
            invoice.subtotal = result.get("subtotal")
            invoice.discount_total = result.get("discount_total")
            invoice.grand_total = result.get("grand_total")
            invoice.raw_extraction = result.get("raw_json")

            # Check for duplicate invoice number
            inv_num = result.get("invoice_number")
            if inv_num:
                dup_result = await db.execute(
                    select(Invoice).where(
                        Invoice.invoice_number == inv_num,
                        Invoice.id != invoice_id,
                    ).limit(1)
                )
                duplicate = dup_result.scalar_one_or_none()
                if duplicate:
                    logger.warning(
                        "Duplicate invoice number '%s' — also exists as invoice id=%d",
                        inv_num, duplicate.id,
                    )
                    invoice.error_message = (
                        f"Warning: Invoice number '{inv_num}' already exists "
                        f"(Invoice #{duplicate.id}). This may be a duplicate."
                    )

            # Auto-detect supplier
            supplier_name = result.get("supplier_name")
            if supplier_name:
                supplier_result = await db.execute(
                    select(Supplier).where(
                        Supplier.name.ilike(f"%{supplier_name}%")
                    ).limit(1)
                )
                supplier = supplier_result.scalar_one_or_none()
                if supplier:
                    invoice.supplier_id = supplier.id
                    logger.info(
                        "Auto-matched supplier: %s (id=%d)",
                        supplier.name,
                        supplier.id,
                    )

            # Create invoice items
            items_data = result.get("items", [])
            if not items_data:
                logger.warning(
                    "Invoice %d: Gemini returned 0 items — image may be blurry or unreadable",
                    invoice_id,
                )
                invoice.status = "failed"
                invoice.error_message = (
                    "No items could be extracted. The image may be blurry, "
                    "unreadable, or not a valid invoice. Try uploading a clearer photo."
                )
                invoice.updated_at = datetime.now(timezone.utc)
                await db.commit()
                return

            for item_data in items_data:
                item = InvoiceItem(
                    invoice_id=invoice_id,
                    line_number=item_data.get("line_number"),
                    extracted_name=item_data.get("extracted_name"),
                    extracted_barcode=item_data.get("extracted_barcode"),
                    extracted_qty=item_data.get("extracted_qty"),
                    extracted_uom=item_data.get("extracted_uom"),
                    extracted_unit_price=item_data.get("extracted_unit_price"),
                    extracted_discount=item_data.get("extracted_discount"),
                    extracted_total=item_data.get("extracted_total"),
                )
                db.add(item)

            # Commit items while status stays "processing" — frontend keeps polling
            invoice.updated_at = datetime.now(timezone.utc)
            await db.commit()

            # Auto-run matching engine (status still "processing")
            try:
                from app.services.matching import match_invoice_items
                match_summary = await match_invoice_items(invoice_id, db)
                logger.info(
                    "Auto-matching for invoice %d: %d/%d matched",
                    invoice_id,
                    match_summary["matched"],
                    match_summary["total"],
                )
            except Exception as match_err:
                logger.warning(
                    "Auto-matching failed for invoice %d (non-fatal): %s",
                    invoice_id,
                    match_err,
                )

            # Set status to "done" AFTER matching — frontend sees final results
            invoice.status = "done"
            invoice.updated_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Extraction complete for invoice %d: %d items extracted",
                invoice_id,
                len(result.get("items", [])),
            )

        except Exception as e:
            logger.error(
                "Extraction failed for invoice %d: %s", invoice_id, e
            )
            # Update status to failed
            try:
                invoice = await db.get(Invoice, invoice_id)
                if invoice:
                    invoice.status = "failed"
                    invoice.error_message = str(e)[:1000]
                    invoice.updated_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception:
                logger.error(
                    "Failed to update invoice %d status to failed", invoice_id
                )


@router.post("/{invoice_id}/reprocess", response_model=InvoiceResponse)
async def reprocess_invoice(
    invoice_id: int,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    """Re-trigger Gemini extraction for an existing invoice.

    Downloads images from R2 and runs extraction again.
    Deletes existing items before re-extracting.
    """
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.image_urls:
        raise HTTPException(
            status_code=400,
            detail="No images stored for this invoice — cannot reprocess",
        )

    # Delete existing items
    existing_items = await db.execute(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id)
    )
    for item in existing_items.scalars().all():
        await db.delete(item)

    # Reset invoice state
    invoice.status = "pending"
    invoice.error_message = None
    invoice.raw_extraction = None
    invoice.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(invoice)

    # Download files from R2 and re-extract
    background_tasks.add_task(
        _reprocess_extraction, invoice_id, invoice.image_urls
    )

    return invoice


async def _reprocess_extraction(
    invoice_id: int, image_keys: list[str]
) -> None:
    """Background task: download images from R2 and re-run extraction."""
    from app.services.storage import download_file

    files: list[tuple[bytes, str]] = []
    for key in image_keys:
        if key.startswith("local://"):
            logger.warning("Cannot reprocess local-only file: %s", key)
            continue
        try:
            data = await download_file(key)
            # Infer mime type from key extension
            mime = "image/jpeg"
            lower = key.lower()
            if lower.endswith(".png"):
                mime = "image/png"
            elif lower.endswith(".pdf"):
                mime = "application/pdf"
            elif lower.endswith(".webp"):
                mime = "image/webp"
            elif lower.endswith(".tiff") or lower.endswith(".tif"):
                mime = "image/tiff"
            files.append((data, mime))
        except Exception as e:
            logger.error("Failed to download %s from R2: %s", key, e)

    if not files:
        async with async_session_factory() as db:
            invoice = await db.get(Invoice, invoice_id)
            if invoice:
                invoice.status = "failed"
                invoice.error_message = "No files could be downloaded from storage"
                await db.commit()
        return

    await _process_extraction(invoice_id, files)


@router.post("/{invoice_id}/match", response_model=MatchSummaryResponse)
async def match_invoice(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Run the matching engine on an invoice's extracted items.

    Matches items against the product database using:
    barcode → exact name → fuzzy match (rapidfuzz).
    """
    from app.services.matching import match_invoice_items

    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"Invoice must be in 'done' status to match (current: {invoice.status})",
        )

    summary = await match_invoice_items(invoice_id, db)
    return summary


@router.put(
    "/{invoice_id}/items/{item_id}/match",
    response_model=InvoiceItemResponse,
)
async def manual_match(
    invoice_id: int,
    item_id: int,
    body: InvoiceItemManualMatch,
    db: AsyncSession = Depends(get_db),
):
    """Manually match an invoice item to a product."""
    from app.services.matching import manual_match_item

    # Verify the item belongs to this invoice
    item = await db.get(InvoiceItem, item_id)
    if not item or item.invoice_id != invoice_id:
        raise HTTPException(
            status_code=404,
            detail="Invoice item not found for this invoice",
        )

    try:
        updated = await manual_match_item(item_id, body.product_id, db)
        return updated
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get(
    "/{invoice_id}/items/{item_id}/suggestions",
    response_model=list[ProductSuggestion],
)
async def get_suggestions(
    invoice_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get top product suggestions for an invoice item based on AI matching."""
    from app.services.matching import get_item_suggestions

    item = await db.get(InvoiceItem, item_id)
    if not item or item.invoice_id != invoice_id:
        raise HTTPException(
            status_code=404,
            detail="Invoice item not found for this invoice",
        )

    suggestions = await get_item_suggestions(item_id, db, limit=10)
    return suggestions


@router.get(
    "/{invoice_id}/suggestions",
    response_model=dict[str, list[ProductSuggestion]],
)
async def get_batch_suggestions(
    invoice_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get suggestions for ALL unmatched items of an invoice in one call.

    Returns {item_id: [suggestions...]}. Much faster than N separate calls.
    """
    from app.services.matching import get_invoice_suggestions

    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    suggestions_map = await get_invoice_suggestions(invoice_id, db, limit=10)
    # Convert int keys to string keys for JSON serialization
    return {str(k): v for k, v in suggestions_map.items()}
