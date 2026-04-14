import logging
import re
from decimal import Decimal

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice_item import InvoiceItem
from app.models.product import Product

logger = logging.getLogger(__name__)

# ── Confidence thresholds ──
BARCODE_CONFIDENCE = Decimal("1.00")
BARCODE_PARTIAL_CONFIDENCE = Decimal("0.90")
EXACT_NAME_CONFIDENCE = Decimal("0.95")
FUZZY_THRESHOLD = 55  # minimum score to consider a match (was 75 — too strict)
REVIEW_THRESHOLD = Decimal("0.65")  # below this → needs manual review (was 0.75)

# ── Common abbreviation normalization ──
ABBREVIATIONS: dict[str, str] = {
    "pkt": "packet",
    "btl": "bottle",
    "ctn": "carton",
    "bx": "box",
    "dz": "dozen",
    "dzn": "dozen",
    "pcs": "pieces",
    "pc": "piece",
    "ea": "each",
    "kg": "kilogram",
    "gm": "gram",
    "grm": "gram",
    "ltr": "liter",
    "lt": "liter",
    "ml": "milliliter",
    "org": "original",
    "orig": "original",
    "sml": "small",
    "med": "medium",
    "lrg": "large",
    "lg": "large",
    "blk": "black",
    "wht": "white",
    "grn": "green",
}


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


def _normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, expand abbreviations, strip noise."""
    text = text.strip().lower()
    # Remove common noise characters
    text = re.sub(r'[*#@!~`]', '', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    # Expand known abbreviations
    words = text.split()
    expanded = [ABBREVIATIONS.get(w, w) for w in words]
    return " ".join(expanded)


def _multi_strategy_score(name_a: str, name_b: str) -> float:
    """Run multiple fuzzy matching strategies and return the best score.

    Strategies:
    1. token_sort_ratio — handles reordered words (e.g., "SOKARI ALHARAMAIN" vs "ALHARAMAIN SOKARI")
    2. partial_ratio — handles substring matches (e.g., "SOKARI" vs "ALHARAMAIN SOKARI 50ML")
    3. token_set_ratio — handles extra/missing words (e.g., "PERFUME OIL 50ML" vs "PERFUME OIL")
    4. WRatio — weighted combination of multiple strategies
    """
    scores = [
        fuzz.token_sort_ratio(name_a, name_b),
        fuzz.partial_ratio(name_a, name_b),
        fuzz.token_set_ratio(name_a, name_b),
        fuzz.WRatio(name_a, name_b),
    ]
    return max(scores)


def _word_overlap_score(name_a: str, name_b: str) -> float:
    """Score based on percentage of shared words. Good for catching
    partial names like 'CHICKEN BREAST' in 'FROZEN CHICKEN BREAST 1KG'."""
    words_a = set(name_a.split())
    words_b = set(name_b.split())
    if not words_a or not words_b:
        return 0.0
    overlap = words_a & words_b
    # Score = overlap relative to the smaller set (the query is usually shorter)
    smaller = min(len(words_a), len(words_b))
    return (len(overlap) / smaller) * 100 if smaller else 0.0


def _match_single_item(
    item: InvoiceItem,
    barcode_map: dict[str, "Product"],
    desc_map: dict[str, "Product"],
    all_products: list["Product"],
) -> dict:
    """Try to match a single invoice item against the product database.

    Matching cascade:
      1. Exact barcode match (confidence 1.00)
      2. Partial barcode match — prefix/suffix (confidence 0.90)
      3. Exact description match, case-insensitive (confidence 0.95)
      4. Multi-strategy fuzzy match with abbreviation normalization
      5. Word-overlap boost for partial name matches
      6. No match — flagged for review

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

        # --- Priority 2: Partial barcode match (prefix/suffix for OCR truncation) ---
        if len(barcode) >= 4:
            for db_barcode, product in barcode_map.items():
                # Check if one is a prefix/suffix of the other
                if (
                    db_barcode.startswith(barcode)
                    or db_barcode.endswith(barcode)
                    or barcode.startswith(db_barcode)
                    or barcode.endswith(db_barcode)
                ):
                    uom_mismatch = _check_uom_mismatch(item.extracted_uom, product.uom)
                    logger.info(
                        "Partial barcode match: extracted '%s' ≈ product '%s' (%s)",
                        barcode, db_barcode, product.description,
                    )
                    return {
                        "product_id": product.id,
                        "matched": True,
                        "confidence": BARCODE_PARTIAL_CONFIDENCE,
                        "method": "barcode_partial",
                        "product_name": product.description,
                        "uom_mismatch": uom_mismatch,
                    }

    if not item.extracted_name:
        return no_match

    name = item.extracted_name.strip()
    name_lower = name.lower()
    name_normalized = _normalize_text(name)

    # --- Priority 3: Exact description match (case-insensitive) ---
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

    # Also try with normalized text
    for desc_key, product in desc_map.items():
        if _normalize_text(desc_key) == name_normalized:
            uom_mismatch = _check_uom_mismatch(item.extracted_uom, product.uom)
            return {
                "product_id": product.id,
                "matched": True,
                "confidence": EXACT_NAME_CONFIDENCE,
                "method": "exact_name_normalized",
                "product_name": product.description,
                "uom_mismatch": uom_mismatch,
            }

    # --- Priority 4: Multi-strategy fuzzy match ---
    if not all_products:
        return no_match

    best_score = 0.0
    best_product = None

    for product in all_products:
        prod_normalized = _normalize_text(product.description)

        # Multi-strategy fuzzy score
        fuzzy_score = _multi_strategy_score(name_normalized, prod_normalized)

        # Word overlap boost — if many words match, boost score
        overlap_score = _word_overlap_score(name_normalized, prod_normalized)

        # Combined score: weighted average favoring the better strategy
        combined = max(fuzzy_score, overlap_score * 0.95)

        if combined > best_score:
            best_score = combined
            best_product = product

    if best_score >= FUZZY_THRESHOLD and best_product is not None:
        confidence = Decimal(str(round(best_score / 100, 2)))
        matched = confidence >= REVIEW_THRESHOLD
        uom_mismatch = _check_uom_mismatch(item.extracted_uom, best_product.uom)

        logger.info(
            "Fuzzy match: '%s' → '%s' (score=%.1f, confidence=%s, matched=%s)",
            name, best_product.description, best_score, confidence, matched,
        )

        return {
            "product_id": best_product.id,
            "matched": matched,
            "confidence": confidence,
            "method": "fuzzy",
            "product_name": best_product.description,
            "uom_mismatch": uom_mismatch,
        }

    # --- Priority 5: No match ---
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
