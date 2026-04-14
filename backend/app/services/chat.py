"""Chat service — conversational AI assistant powered by Gemini.

Provides deep, context-aware responses using the FULL invoice database:
products (with barcodes), suppliers, invoices with line items, and analytics.
Uses intelligent query parsing to enrich context based on user intent.
"""

import asyncio
import json
import logging
import re

from google import genai
from google.genai import types
from sqlalchemy import select, func, or_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.product import Product
from app.models.supplier import Supplier

logger = logging.getLogger(__name__)

MAX_RETRIES = 2  # retries per key+model combination
RETRY_DELAY = 2  # seconds between retries

# ---------------------------------------------------------------------------
# System prompt — comprehensive, schema-aware, with clear instructions
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert AI accounting assistant embedded in a small-business invoice processing system.
You have FULL read access to the business database. All data is provided below.

━━━ YOUR CAPABILITIES ━━━
• Search and retrieve any invoice by number, supplier, date, product, amount, or keyword.
• Look up products by name, barcode, brand, category, or partial match.
• Show detailed invoice breakdowns with every line item, quantities, prices, totals.
• Provide spending analytics: totals per supplier, per month, per product.
• Analyze receipt/invoice images the user sends and extract data from them.
• Compare extracted invoice items against the product catalog.
• Explain matching results (barcode match, fuzzy match, unmatched items).
• Give insights on pricing trends, spending patterns, and anomalies.

━━━ HOW TO ANSWER ━━━
• When the user asks for "the invoice of X" or "invoice for X", search by supplier name, invoice number, product name, or any keyword in the data below. Be flexible — try partial matches.
• When showing invoice data, present it in a clean table format with columns.
• Always include barcodes when showing product or invoice item details.
• Format all currency with 2 decimal places and the correct currency code.
• If multiple invoices match, show all of them and let the user choose.
• When asked about a product, show: barcode, description, brand, UOM, cost, price.
• If the user asks about matching, explain the confidence score and method used.
• Be proactive — if you see related useful information, mention it.
• Never say "I don't have access to the database" — you DO, it's all below.
• If a search returns no results, suggest alternative searches or partial matches.
• Answer in the same language the user writes in (English, Arabic, Malay, etc.)

━━━ DATABASE SCHEMA ━━━
Tables: suppliers, products, invoices, invoice_items

Supplier: id, name, address, phone, bank_name, bank_account, notes
Product: id, stock_id, barcode (unique), description, uom, cost, price, brand, group_name, category, balance_qty, is_active
Invoice: id, invoice_number, supplier_id, status (pending/processing/done/failed), invoice_date, currency, subtotal, discount_total, grand_total
InvoiceItem: id, invoice_id, product_id, line_number, extracted_name, extracted_barcode, extracted_qty, extracted_uom, extracted_unit_price, extracted_discount, extracted_total, matched (bool), match_confidence, match_method

━━━ FULL DATABASE CONTENTS ━━━
{db_context}
"""


# ---------------------------------------------------------------------------
# Database context builder — deep, comprehensive, and query-aware
# ---------------------------------------------------------------------------

async def _build_db_context(db: AsyncSession, user_message: str = "") -> str:
    """Build comprehensive database context for the AI.

    Includes ALL suppliers, ALL invoices with their line items and match info,
    product catalog, and spending analytics. Also adds query-specific context
    based on keywords detected in the user's message.
    """
    sections: list[str] = []

    # ── 1. Summary statistics ──
    total_invoices = (await db.execute(select(func.count(Invoice.id)))).scalar() or 0
    done_invoices = (
        await db.execute(
            select(func.count(Invoice.id)).where(Invoice.status == "done")
        )
    ).scalar() or 0
    pending_invoices = (
        await db.execute(
            select(func.count(Invoice.id)).where(
                Invoice.status.in_(["pending", "processing"])
            )
        )
    ).scalar() or 0
    failed_invoices = (
        await db.execute(
            select(func.count(Invoice.id)).where(Invoice.status == "failed")
        )
    ).scalar() or 0
    product_count = (
        await db.execute(select(func.count(Product.id)).where(Product.is_active == True))  # noqa: E712
    ).scalar() or 0
    total_items = (await db.execute(select(func.count(InvoiceItem.id)))).scalar() or 0
    matched_items = (
        await db.execute(
            select(func.count(InvoiceItem.id)).where(InvoiceItem.matched == True)  # noqa: E712
        )
    ).scalar() or 0
    match_rate = (matched_items / total_items * 100) if total_items else 0

    # Total spend
    total_spend_result = await db.execute(
        select(func.sum(Invoice.grand_total)).where(Invoice.status == "done")
    )
    total_spend = total_spend_result.scalar() or 0

    sections.append(
        f"[SUMMARY]\n"
        f"Invoices: {total_invoices} total ({done_invoices} done, {pending_invoices} pending, {failed_invoices} failed)\n"
        f"Products in catalog: {product_count}\n"
        f"Line items extracted: {total_items} | Matched: {matched_items} ({match_rate:.1f}%)\n"
        f"Total spend (done invoices): {total_spend:.2f}"
    )

    # ── 2. ALL Suppliers ──
    supplier_result = await db.execute(
        select(Supplier).order_by(Supplier.name)
    )
    suppliers = supplier_result.scalars().all()
    supplier_map = {s.id: s.name for s in suppliers}

    if suppliers:
        sup_lines = ["\n[SUPPLIERS]"]
        sup_lines.append("ID | Name | Phone | Bank | Address")
        sup_lines.append("---|------|-------|------|--------")
        for s in suppliers:
            sup_lines.append(
                f"{s.id} | {s.name} | {s.phone or '-'} | "
                f"{s.bank_name or '-'} ({s.bank_account or '-'}) | "
                f"{(s.address or '-')[:60]}"
            )
        sections.append("\n".join(sup_lines))

    # ── 3. ALL Invoices with their line items ──
    inv_result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items).selectinload(InvoiceItem.product))
        .order_by(Invoice.created_at.desc())
        .limit(100)
    )
    invoices = inv_result.scalars().unique().all()

    if invoices:
        inv_lines = ["\n[INVOICES WITH LINE ITEMS]"]
        for inv in invoices:
            supplier_name = supplier_map.get(inv.supplier_id, "Unknown")
            inv_lines.append(
                f"\n▸ Invoice #{inv.id} | Number: {inv.invoice_number or 'N/A'} | "
                f"Supplier: {supplier_name} (id={inv.supplier_id or '?'}) | "
                f"Date: {inv.invoice_date or '?'} | Status: {inv.status} | "
                f"Currency: {inv.currency} | "
                f"Subtotal: {inv.subtotal or '?'} | Discount: {inv.discount_total or 0} | "
                f"Grand Total: {inv.grand_total or '?'}"
            )
            if inv.items:
                inv_lines.append(
                    "  Ln | Extracted Name | Barcode | Qty | UOM | "
                    "Unit Price | Discount% | Total | Matched? | Confidence | Method | Matched Product"
                )
                for item in sorted(inv.items, key=lambda x: x.line_number or 0):
                    product_name = ""
                    if item.product:
                        product_name = f"{item.product.description} (barcode: {item.product.barcode})"
                    inv_lines.append(
                        f"  {item.line_number or '?'} | "
                        f"{item.extracted_name or '?'} | "
                        f"{item.extracted_barcode or '-'} | "
                        f"{item.extracted_qty or '?'} | "
                        f"{item.extracted_uom or '-'} | "
                        f"{item.extracted_unit_price or '?'} | "
                        f"{item.extracted_discount or '-'} | "
                        f"{item.extracted_total or '?'} | "
                        f"{'✓' if item.matched else '✗'} | "
                        f"{item.match_confidence or '-'} | "
                        f"{item.match_method or '-'} | "
                        f"{product_name or 'UNMATCHED'}"
                    )
            else:
                inv_lines.append("  (no items)")
        sections.append("\n".join(inv_lines))

    # ── 4. Product catalog (compact format) ──
    prod_result = await db.execute(
        select(Product)
        .where(Product.is_active == True)  # noqa: E712
        .order_by(Product.description)
        .limit(500)
    )
    products = prod_result.scalars().all()

    if products:
        prod_lines = [f"\n[PRODUCT CATALOG — {product_count} total, showing {len(products)}]"]
        prod_lines.append("ID | Barcode | Description | Brand | Category | Group | UOM | Cost | Price")
        prod_lines.append("---|---------|-------------|-------|----------|-------|-----|------|------")
        for p in products:
            prod_lines.append(
                f"{p.id} | {p.barcode} | {p.description} | "
                f"{p.brand or '-'} | {p.category or '-'} | "
                f"{p.group_name or '-'} | {p.uom} | "
                f"{p.cost:.2f} | {p.price:.2f}"
            )
        sections.append("\n".join(prod_lines))

    # ── 5. Spending analytics ──
    if invoices:
        # Per-supplier spending
        supplier_spend: dict[str, float] = {}
        for inv in invoices:
            if inv.status == "done" and inv.grand_total:
                sname = supplier_map.get(inv.supplier_id, "Unknown")
                supplier_spend[sname] = supplier_spend.get(sname, 0) + float(inv.grand_total)

        if supplier_spend:
            analytics_lines = ["\n[SPENDING BY SUPPLIER]"]
            for sname, total in sorted(supplier_spend.items(), key=lambda x: -x[1]):
                analytics_lines.append(f"  {sname}: {total:.2f}")
            sections.append("\n".join(analytics_lines))

    # ── 6. Query-specific enrichment ──
    extra = await _query_specific_context(db, user_message, products, invoices)
    if extra:
        sections.append(f"\n[QUERY-SPECIFIC RESULTS]\n{extra}")

    return "\n".join(sections)


async def _query_specific_context(
    db: AsyncSession,
    message: str,
    products_already_loaded: list[Product],
    invoices_already_loaded: list[Invoice],
) -> str:
    """Parse user message for specific references and fetch targeted data."""
    if not message:
        return ""

    msg_lower = message.lower()
    extra_parts: list[str] = []

    # Detect invoice number references (e.g., "INV-001", "#123", "invoice 5")
    inv_number_patterns = re.findall(
        r'(?:invoice|inv|#)\s*[-#]?\s*(\w[\w-]*\d[\w-]*)',
        msg_lower,
    )

    if inv_number_patterns:
        for pattern in inv_number_patterns:
            result = await db.execute(
                select(Invoice)
                .options(selectinload(Invoice.items).selectinload(InvoiceItem.product))
                .where(
                    or_(
                        Invoice.invoice_number.ilike(f"%{pattern}%"),
                        cast(Invoice.id, String) == pattern,
                    )
                )
            )
            found = result.scalars().unique().all()
            if found:
                extra_parts.append(
                    f"Found {len(found)} invoice(s) matching '{pattern}'"
                )

    # Detect barcode references (numeric strings 4+ digits)
    barcode_refs = re.findall(r'\b(\d{4,})\b', message)
    if barcode_refs:
        for barcode in barcode_refs:
            # Search products
            prod_result = await db.execute(
                select(Product).where(Product.barcode.ilike(f"%{barcode}%"))
            )
            found_products = prod_result.scalars().all()
            if found_products:
                for p in found_products:
                    extra_parts.append(
                        f"Barcode '{barcode}' → Product: {p.description} "
                        f"(barcode: {p.barcode}, brand: {p.brand or '-'}, "
                        f"cost: {p.cost:.2f}, price: {p.price:.2f})"
                    )

            # Search invoice items with this barcode
            item_result = await db.execute(
                select(InvoiceItem)
                .where(InvoiceItem.extracted_barcode.ilike(f"%{barcode}%"))
                .limit(10)
            )
            found_items = item_result.scalars().all()
            if found_items:
                extra_parts.append(
                    f"Barcode '{barcode}' appears in {len(found_items)} invoice item(s): "
                    + ", ".join(f"invoice #{it.invoice_id} line {it.line_number}" for it in found_items)
                )

    # Detect product name searches — look for keywords in product descriptions
    # Extract potential product-name keywords (2+ word sequences, excluding common words)
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "of", "for", "in", "on",
        "to", "and", "or", "with", "from", "by", "at", "this", "that", "it",
        "me", "my", "give", "show", "find", "get", "what", "which", "how",
        "much", "many", "total", "all", "invoice", "invoices", "product",
        "products", "supplier", "suppliers", "price", "cost", "can", "you",
        "please", "i", "want", "need", "about", "tell", "do", "does", "have",
        "has", "item", "items", "detail", "details",
    }
    words = re.findall(r'[a-zA-Z\u0600-\u06FF]{2,}', msg_lower)
    search_words = [w for w in words if w not in stop_words]

    if search_words and len(search_words) <= 8:
        # Search products by description for each meaningful word
        for word in search_words:
            if len(word) < 3:
                continue
            prod_result = await db.execute(
                select(Product)
                .where(Product.description.ilike(f"%{word}%"))
                .limit(10)
            )
            found = prod_result.scalars().all()
            if found:
                extra_parts.append(
                    f"Products matching '{word}': "
                    + "; ".join(
                        f"{p.description} (barcode: {p.barcode}, cost: {p.cost:.2f})"
                        for p in found
                    )
                )

            # Also search invoice items by extracted name
            item_result = await db.execute(
                select(InvoiceItem)
                .options(selectinload(InvoiceItem.invoice))
                .where(InvoiceItem.extracted_name.ilike(f"%{word}%"))
                .limit(10)
            )
            found_items = item_result.scalars().all()
            if found_items:
                extra_parts.append(
                    f"Invoice items matching '{word}': "
                    + "; ".join(
                        f"'{it.extracted_name}' in invoice #{it.invoice_id} "
                        f"(qty: {it.extracted_qty}, total: {it.extracted_total})"
                        for it in found_items
                    )
                )

    return "\n".join(extra_parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_api_keys() -> list[str]:
    """Return all configured, non-empty Gemini API keys."""
    settings = get_settings()
    keys = []
    for k in [settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_2]:
        if k and k not in ("", "your_gemini_api_key_here"):
            keys.append(k)
    return keys


def _classify_error(error: Exception) -> str:
    """Classify a Gemini API error into a category for retry decisions."""
    msg = str(error).lower()
    if "401" in msg or "unauthenticated" in msg or "invalid" in msg:
        return "auth"          # bad/expired key → try next key
    if "429" in msg or "rate" in msg or "quota" in msg or "resource" in msg:
        return "rate_limit"    # rate limited → retry after delay or next key
    if "500" in msg or "503" in msg or "unavailable" in msg or "internal" in msg:
        return "server"        # transient server error → retry
    if "timeout" in msg or "deadline" in msg:
        return "timeout"       # timeout → retry
    return "unknown"


def _user_friendly_error(error_type: str, last_error: Exception) -> str:
    """Return a user-facing error message based on the error type."""
    if error_type == "auth":
        return (
            "The AI service credentials are invalid or expired. "
            "Please contact the administrator to update the API key."
        )
    if error_type == "rate_limit":
        return (
            "The AI service is temporarily overloaded. "
            "Please wait a moment and try again."
        )
    if error_type == "server":
        return (
            "The AI service is experiencing temporary issues. "
            "Please try again in a few seconds."
        )
    if error_type == "timeout":
        return (
            "The AI request timed out. Try asking a simpler question "
            "or try again in a moment."
        )
    return "The AI assistant encountered an unexpected error. Please try again."


# ---------------------------------------------------------------------------
# Main chat function
# ---------------------------------------------------------------------------

async def chat_with_ai(
    message: str,
    image_data: list[tuple[bytes, str]] | None,
    conversation_history: list[dict],
    db: AsyncSession,
) -> str:
    """Send a message (with optional images) to Gemini and get a response.

    Robustness features:
    - Multiple API key rotation (if GEMINI_API_KEY_2 is set)
    - Model cascade: primary → fallback
    - Retry with delay for transient errors
    - Specific, user-friendly error messages

    Args:
        message: The user's text message.
        image_data: Optional list of (bytes, mime_type) for attached images.
        conversation_history: List of previous messages [{role, text}].
        db: Database session for context.

    Returns:
        The AI assistant's response text.
    """
    settings = get_settings()
    api_keys = _get_api_keys()

    if not api_keys:
        raise ValueError(
            "The AI service is not configured. "
            "Please set GEMINI_API_KEY in the server environment."
        )

    # Build deep database context (query-aware)
    db_context = await _build_db_context(db, user_message=message)
    system_instruction = SYSTEM_PROMPT.format(db_context=db_context)

    # Build conversation contents
    contents: list[types.Content] = []

    # Add conversation history
    for msg in conversation_history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["text"])],
            )
        )

    # Build current message parts
    current_parts: list[types.Part] = []

    # Add images if present
    if image_data:
        for img_bytes, mime_type in image_data:
            current_parts.append(
                types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
            )

    # Add text message
    current_parts.append(types.Part.from_text(text=message))

    contents.append(
        types.Content(role="user", parts=current_parts)
    )

    logger.info(
        "Chat request: %d history messages, %d images, message length: %d, "
        "context length: %d chars, api_keys: %d",
        len(conversation_history),
        len(image_data) if image_data else 0,
        len(message),
        len(system_instruction),
        len(api_keys),
    )

    # ── Robust model cascade with key rotation ──
    models_to_try = [settings.GEMINI_PRIMARY_MODEL, settings.GEMINI_FALLBACK_MODEL]
    last_error: Exception | None = None
    last_error_type = "unknown"

    for key_index, api_key in enumerate(api_keys):
        client = genai.Client(api_key=api_key)
        key_label = f"key_{key_index + 1}"

        for model_index, model_name in enumerate(models_to_try):
            is_primary = model_index == 0

            # Gemini 3.x models use thinking_level; 2.x models don't.
            thinking = (
                types.ThinkingConfig(thinking_level="HIGH")
                if is_primary
                else None
            )

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.4,
                            thinking_config=thinking,
                        ),
                    )
                    logger.info(
                        "Chat responded via %s [%s] (attempt %d)",
                        model_name, key_label, attempt,
                    )
                    reply = response.text
                    logger.info("Chat response: %d chars", len(reply))
                    return reply

                except Exception as e:
                    last_error = e
                    last_error_type = _classify_error(e)
                    logger.warning(
                        "Chat %s [%s] attempt %d/%d failed (%s): %s",
                        model_name, key_label, attempt, MAX_RETRIES,
                        last_error_type, e,
                    )

                    # Auth errors → skip remaining retries, try next key
                    if last_error_type == "auth":
                        break

                    # Retry transient errors with delay
                    if attempt < MAX_RETRIES and last_error_type in (
                        "rate_limit", "server", "timeout"
                    ):
                        await asyncio.sleep(RETRY_DELAY * attempt)

            # If auth error, skip remaining models for this key
            if last_error_type == "auth":
                logger.error("API %s is invalid/expired, trying next key", key_label)
                break

    # All keys + models + retries exhausted
    error_msg = _user_friendly_error(last_error_type, last_error)
    logger.error(
        "Chat failed after all attempts. Error type: %s, Last error: %s",
        last_error_type, last_error,
    )
    raise ValueError(error_msg)
