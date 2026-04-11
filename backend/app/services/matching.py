import logging
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice_item import InvoiceItem
from app.models.product import Product

logger = logging.getLogger(__name__)

# Confidence thresholds
BARCODE_CONFIDENCE = Decimal("1.00")
EXACT_NAME_CONFIDENCE = Decimal("0.95")
FUZZY_THRESHOLD = 75  # minimum rapidfuzz score to consider a match
REVIEW_THRESHOLD = Decimal("0.75")  # below this = needs manual review


async def match_invoice_items(
    invoice_id: int,
    db: AsyncSession,
) -> dict:
    """Run the matching engine on all items of an invoice.

    Priority cascade:
      1. Exact barcode match (confidence 1.00)
      2. Exact description match, case-insensitive (confidence 0.95)
      3. Fuzzy description match via rapidfuzz (confidence = score/100)
      4. No match — flagged for review

    Returns a summary dict with match statistics.
    """
    # Load all invoice items
    result = await db.execute(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id)
        .order_by(InvoiceItem.line_number)
    )
    items = result.scalars().all()

    if not items:
        return {"total": 0, "matched": 0, "unmatched": 0, "items": []}

    # Load all active products into memory for matching
    prod_result = await db.execute(
        select(Product).where(Product.is_active == True)  # noqa: E712
    )
    products = prod_result.scalars().all()

    # Build lookup structures
    barcode_map: dict[str, Product] = {}
    desc_map: dict[str, Product] = {}  # lowercase description -> product
    all_products: list[Product] = []

    for p in products:
        if p.barcode:
            barcode_map[p.barcode.strip()] = p
        desc_map[p.description.strip().lower()] = p
        all_products.append(p)

    matched_count = 0
    unmatched_count = 0
    item_results = []

    for item in items:
        match_result = _match_single_item(item, barcode_map, desc_map, all_products)

        item.product_id = match_result["product_id"]
        item.matched = match_result["matched"]
        item.match_confidence = match_result["confidence"]
        item.match_method = match_result["method"]

        if match_result["matched"]:
            matched_count += 1
        else:
            unmatched_count += 1

        item_results.append({
            "item_id": item.id,
            "line_number": item.line_number,
            "extracted_name": item.extracted_name,
            "product_id": match_result["product_id"],
            "product_name": match_result.get("product_name"),
            "matched": match_result["matched"],
            "confidence": float(match_result["confidence"]) if match_result["confidence"] else None,
            "method": match_result["method"],
            "uom_mismatch": match_result.get("uom_mismatch", False),
        })

    await db.commit()

    summary = {
        "total": len(items),
        "matched": matched_count,
        "unmatched": unmatched_count,
        "match_rate": matched_count / len(items) if items else 0,
        "items": item_results,
    }

    logger.info(
        "Matching complete for invoice %d: %d/%d matched (%.0f%%)",
        invoice_id,
        matched_count,
        len(items),
        summary["match_rate"] * 100,
    )

    return summary


def _match_single_item(
    item: InvoiceItem,
    barcode_map: dict[str, "Product"],
    desc_map: dict[str, "Product"],
    all_products: list["Product"],
) -> dict:
    """Try to match a single invoice item against the product database.

    Returns a dict with: product_id, matched, confidence, method, product_name, uom_mismatch
    """
    no_match = {
        "product_id": None,
        "matched": False,
        "confidence": None,
        "method": None,
        "product_name": None,
        "uom_mismatch": False,
    }

    # --- Priority 1: Exact barcode match ---
    if item.extracted_barcode:
        barcode = item.extracted_barcode.strip()
        if barcode in barcode_map:
            product = barcode_map[barcode]
            uom_mismatch = _check_uom_mismatch(item.extracted_uom, product.uom)
            return {
                "product_id": product.id,
                "matched": True,
                "confidence": BARCODE_CONFIDENCE,
                "method": "barcode",
                "product_name": product.description,
                "uom_mismatch": uom_mismatch,
            }

    if not item.extracted_name:
        return no_match

    name = item.extracted_name.strip()
    name_lower = name.lower()

    # --- Priority 2: Exact description match (case-insensitive) ---
    if name_lower in desc_map:
        product = desc_map[name_lower]
        uom_mismatch = _check_uom_mismatch(item.extracted_uom, product.uom)
        return {
            "product_id": product.id,
            "matched": True,
            "confidence": EXACT_NAME_CONFIDENCE,
            "method": "exact_name",
            "product_name": product.description,
            "uom_mismatch": uom_mismatch,
        }

    # --- Priority 3: Fuzzy description match ---
    if not all_products:
        return no_match

    best_score = 0
    best_product = None

    for product in all_products:
        # Use token_sort_ratio — handles reordered words well
        # e.g. "ALHARAMAIN SOKARI" vs "SOKARI ALHARAMAIN"
        score = fuzz.token_sort_ratio(name_lower, product.description.lower())
        if score > best_score:
            best_score = score
            best_product = product

    if best_score >= FUZZY_THRESHOLD and best_product is not None:
        confidence = Decimal(str(round(best_score / 100, 2)))
        matched = confidence >= REVIEW_THRESHOLD
        uom_mismatch = _check_uom_mismatch(item.extracted_uom, best_product.uom)
        return {
            "product_id": best_product.id,
            "matched": matched,
            "confidence": confidence,
            "method": "fuzzy",
            "product_name": best_product.description,
            "uom_mismatch": uom_mismatch,
        }

    # --- Priority 4: No match ---
    return no_match


def _check_uom_mismatch(extracted_uom: str | None, product_uom: str | None) -> bool:
    """Check if there's a UOM mismatch between invoice and product.

    Returns True if there's a mismatch that needs attention.
    """
    if not extracted_uom or not product_uom:
        return False

    # Normalize: strip whitespace, uppercase
    ext = extracted_uom.strip().upper()
    prod = product_uom.strip().upper()

    if ext == prod:
        return False

    # Handle common equivalent UOMs
    equivalents = [
        {"PCS", "PC", "PIECE", "PIECES", "UNIT", "UNITS", "EA"},
        {"CTN", "CARTON", "CARTONS"},
        {"BOX", "BOXES", "BX"},
        {"PKT", "PAKET", "PACKET", "PACKETS", "PACK", "PACKS"},
        {"BTL", "BOTTLE", "BOTTLES"},
        {"DZN", "DOZEN", "DOZ"},
        {"KG", "KILOGRAM", "KILOGRAMS"},
    ]

    for group in equivalents:
        # Strip numeric suffixes like "CTN-12", "BOX(5KG)"
        ext_base = ext.split("-")[0].split("(")[0]
        prod_base = prod.split("-")[0].split("(")[0]
        if ext_base in group and prod_base in group:
            return False

    return True


async def manual_match_item(
    item_id: int,
    product_id: int,
    db: AsyncSession,
) -> InvoiceItem:
    """Manually match an invoice item to a product.

    Sets match_method='manual' and match_confidence=1.00.
    """
    item = await db.get(InvoiceItem, item_id)
    if not item:
        raise ValueError(f"Invoice item {item_id} not found")

    product = await db.get(Product, product_id)
    if not product:
        raise ValueError(f"Product {product_id} not found")

    item.product_id = product_id
    item.matched = True
    item.match_confidence = Decimal("1.00")
    item.match_method = "manual"

    await db.commit()
    await db.refresh(item)

    logger.info(
        "Manual match: item %d → product %d (%s)",
        item_id,
        product_id,
        product.description,
    )

    return item
