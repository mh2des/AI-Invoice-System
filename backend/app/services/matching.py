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
    # Remove common noise characters and packaging info like (1*12)
    text = re.sub(r'[*#@!~`]', '', text)
    text = re.sub(r'\([\d*x]+\)', '', text)  # remove (1*12), (1x12) etc.
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Expand known abbreviations
    words = text.split()
    expanded = [ABBREVIATIONS.get(w, w) for w in words]
    return " ".join(expanded)


# ── Size/volume extraction for size-aware matching ──

_SIZE_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(ml|lt|ltr|liter|litre|l|kg|kilogram|gm|gram|g|oz|gallon|gal)\b',
    re.IGNORECASE,
)

# Normalize all volumes to milliliters and weights to grams for comparison
_UNIT_TO_ML = {
    "ml": 1, "l": 1000, "lt": 1000, "ltr": 1000, "liter": 1000, "litre": 1000,
}
_UNIT_TO_G = {
    "g": 1, "gm": 1, "gram": 1, "kg": 1000, "kilogram": 1000, "oz": 28.35,
}


def _extract_size(text: str) -> tuple[float | None, str | None]:
    """Extract the primary size/volume from a product name.

    Returns (normalized_value, category) where category is 'volume' or 'weight'.
    E.g., '1L' → (1000.0, 'volume'), '200ML' → (200.0, 'volume'), '500G' → (500.0, 'weight')
    """
    matches = _SIZE_PATTERN.findall(text)
    if not matches:
        return None, None

    # Take the first size found
    num_str, unit = matches[0]
    num = float(num_str)
    unit_lower = unit.lower()

    if unit_lower in _UNIT_TO_ML:
        return num * _UNIT_TO_ML[unit_lower], "volume"
    if unit_lower in _UNIT_TO_G:
        return num * _UNIT_TO_G[unit_lower], "weight"
    return None, None


def _size_compatible(name_a: str, name_b: str) -> bool:
    """Check whether two product names have compatible sizes.

    Returns True if:
    - Neither has a size → compatible (can't compare)
    - Only one has a size → compatible (ambiguous, allow match)
    - Both have sizes in same category and values are within 20% → compatible
    - Both have sizes but differ significantly → NOT compatible
    """
    size_a, cat_a = _extract_size(name_a)
    size_b, cat_b = _extract_size(name_b)

    # If either has no size, we can't penalize
    if size_a is None or size_b is None:
        return True

    # Different categories (volume vs weight) → can't compare
    if cat_a != cat_b:
        return True

    # Same category — check if sizes are close (within 20% tolerance)
    if size_a == 0 or size_b == 0:
        return size_a == size_b

    ratio = max(size_a, size_b) / min(size_a, size_b)
    return ratio <= 1.2  # 20% tolerance


def _compute_match_score(name_a: str, name_b: str) -> float:
    """Compute a robust match score between two product names.

    Uses a balanced combination of fuzzy strategies with size-awareness:
    - token_sort_ratio: good for reordered words
    - token_set_ratio: good for extra/missing words (with strict guard)
    - ratio: basic Levenshtein similarity (no partial matching tricks)
    - Size penalty: if sizes clearly differ, penalize heavily

    Does NOT use partial_ratio or WRatio (both cause false positives).
    """
    # Primary scores
    sort_score = fuzz.token_sort_ratio(name_a, name_b)
    set_score = fuzz.token_set_ratio(name_a, name_b)
    plain_score = fuzz.ratio(name_a, name_b)

    # Guard token_set_ratio: it gives 100 when one string is a subset of
    # another's tokens (e.g., "pomegranate" vs "lavi 1l pack pomegranate fruit").
    # Only trust it when there's significant bidirectional word overlap.
    words_a = set(name_a.split())
    words_b = set(name_b.split())
    overlap = len(words_a & words_b)

    # Require overlap to be at least 50% of BOTH word sets
    overlap_ratio_a = overlap / len(words_a) if words_a else 0
    overlap_ratio_b = overlap / len(words_b) if words_b else 0
    min_overlap = min(overlap_ratio_a, overlap_ratio_b)

    if min_overlap < 0.5:
        # Poor overlap — don't trust token_set_ratio at all
        set_score = min(set_score, sort_score)

    base_score = max(sort_score, set_score, plain_score)

    # Size penalty: if both products have sizes and they differ significantly,
    # penalize the score to prevent "1L" matching "200ML"
    if not _size_compatible(name_a, name_b):
        base_score = base_score * 0.5  # halve the score

    return base_score


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

    # --- Priority 4: Size-aware fuzzy match ---
    if not all_products:
        return no_match

    best_score = 0.0
    best_product = None

    for product in all_products:
        prod_normalized = _normalize_text(product.description)
        score = _compute_match_score(name_normalized, prod_normalized)

        if score > best_score:
            best_score = score
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
