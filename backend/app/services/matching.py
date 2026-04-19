import logging
import math
import re
from collections import Counter
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
FUZZY_THRESHOLD = 40           # minimum score to consider as a candidate
AUTO_MATCH_THRESHOLD = 0.65    # above this → auto-matched
SUGGESTION_THRESHOLD = 0.35    # above this → shown as suggestion
MAX_CANDIDATES = 5             # top N candidates returned per item

# ── Stop words (low-value for matching) ──
STOP_WORDS = frozenset({
    "the", "a", "an", "of", "for", "and", "or", "in", "with", "per", "to",
    "is", "at", "by", "from", "on", "no", "not", "new", "free",
})

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
    "choc": "chocolate",
    "strw": "strawberry",
    "straw": "strawberry",
    "van": "vanilla",
    "flv": "flavour",
    "flvr": "flavour",
}


# ═══════════════════════════════════════════════════════════════
# Text normalization
# ═══════════════════════════════════════════════════════════════

def _normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, strip noise, expand abbreviations."""
    text = text.strip().lower()

    # Remove packaging multipliers: "1*50", "1x12", "3 x 4", "24's"
    text = re.sub(r'\d+\s*[*x×]\s*\d+', ' ', text)
    text = re.sub(r"\d+'s\b", ' ', text)

    # Remove parenthesized content like (1*12), (500ML), (PROMO)
    text = re.sub(r'\([^)]*\)', ' ', text)

    # Remove common noise characters
    text = re.sub(r'[*#@!~`"\'{}[\]|\\]', ' ', text)

    # Remove standalone short codes that are likely article/stock codes (e.g., "AL505", "FS-001")
    # Only at start or end to avoid stripping from mid-name
    text = re.sub(r'^[a-z]{1,3}[-]?\d{3,}[a-z]?\s+', ' ', text)
    text = re.sub(r'\s+[a-z]{1,3}[-]?\d{3,}[a-z]?$', ' ', text)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Expand known abbreviations
    words = text.split()
    expanded = [ABBREVIATIONS.get(w, w) for w in words]
    return " ".join(expanded)


def _extract_significant_tokens(text: str) -> set[str]:
    """Extract meaningful tokens, removing stop words and very short tokens."""
    words = set(text.split())
    return {w for w in words if w not in STOP_WORDS and len(w) > 1}


# ═══════════════════════════════════════════════════════════════
# Size/volume extraction for size-aware matching
# ═══════════════════════════════════════════════════════════════

_SIZE_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(ml|lt|ltr|liter|litre|l|kg|kilogram|gm|gram|g|oz|gallon|gal|mm|cm)\b',
    re.IGNORECASE,
)

_UNIT_TO_ML = {
    "ml": 1, "l": 1000, "lt": 1000, "ltr": 1000, "liter": 1000, "litre": 1000,
}
_UNIT_TO_G = {
    "g": 1, "gm": 1, "gram": 1, "kg": 1000, "kilogram": 1000, "oz": 28.35,
}


def _extract_size(text: str) -> tuple[float | None, str | None]:
    """Extract the primary size/volume from a product name."""
    matches = _SIZE_PATTERN.findall(text)
    if not matches:
        return None, None
    num_str, unit = matches[0]
    num = float(num_str)
    unit_lower = unit.lower()
    if unit_lower in _UNIT_TO_ML:
        return num * _UNIT_TO_ML[unit_lower], "volume"
    if unit_lower in _UNIT_TO_G:
        return num * _UNIT_TO_G[unit_lower], "weight"
    return None, None


def _size_compatible(name_a: str, name_b: str) -> bool:
    """Check whether two product names have compatible sizes."""
    size_a, cat_a = _extract_size(name_a)
    size_b, cat_b = _extract_size(name_b)
    if size_a is None or size_b is None:
        return True
    if cat_a != cat_b:
        return True
    if size_a == 0 or size_b == 0:
        return size_a == size_b
    ratio = max(size_a, size_b) / min(size_a, size_b)
    return ratio <= 1.2


# ═══════════════════════════════════════════════════════════════
# Trigram character-level similarity (OCR resilience)
# ═══════════════════════════════════════════════════════════════

def _trigram_similarity(s1: str, s2: str) -> float:
    """Character trigram Jaccard similarity (0-100). Resilient to OCR errors."""
    n = 3
    if len(s1) < n or len(s2) < n:
        return 0.0
    ngrams1 = {s1[i:i + n] for i in range(len(s1) - n + 1)}
    ngrams2 = {s2[i:i + n] for i in range(len(s2) - n + 1)}
    overlap = ngrams1 & ngrams2
    union = ngrams1 | ngrams2
    return (len(overlap) / len(union)) * 100 if union else 0.0


# ═══════════════════════════════════════════════════════════════
# Token importance weighting (lightweight IDF)
# ═══════════════════════════════════════════════════════════════

def _build_idf(products: list["Product"]) -> dict[str, float]:
    """Build inverse document frequency map from product descriptions.

    Rare tokens (brand names, specific flavours) get high IDF.
    Common tokens (juice, drink, water) get low IDF.
    """
    doc_count = len(products)
    if doc_count == 0:
        return {}

    df: Counter = Counter()
    for p in products:
        tokens = _extract_significant_tokens(_normalize_text(p.description))
        for t in tokens:
            df[t] += 1

    idf = {}
    for token, freq in df.items():
        idf[token] = math.log(doc_count / freq) if freq > 0 else 0
    return idf


def _weighted_token_overlap(
    tokens_a: set[str],
    tokens_b: set[str],
    idf: dict[str, float],
) -> float:
    """IDF-weighted Jaccard overlap score (0-100).

    Shared rare tokens (brand names) contribute more than shared common ones.
    """
    if not tokens_a or not tokens_b:
        return 0.0

    overlap = tokens_a & tokens_b
    union = tokens_a | tokens_b

    if not union:
        return 0.0

    default_idf = 2.0
    weighted_overlap = sum(idf.get(t, default_idf) for t in overlap)
    weighted_union = sum(idf.get(t, default_idf) for t in union)

    return (weighted_overlap / weighted_union) * 100 if weighted_union else 0.0


# ═══════════════════════════════════════════════════════════════
# Containment scoring (handles subset names)
# ═══════════════════════════════════════════════════════════════

def _containment_score(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Asymmetric containment: what fraction of the SMALLER set is in the larger?

    Handles cases like invoice "LIGHTER" matching DB "NYC LIGHTER TRANSPARENT".
    Returns 0-100.
    """
    if not tokens_a or not tokens_b:
        return 0.0

    smaller = tokens_a if len(tokens_a) <= len(tokens_b) else tokens_b
    larger = tokens_a if len(tokens_a) > len(tokens_b) else tokens_b

    overlap = smaller & larger
    containment = len(overlap) / len(smaller) if smaller else 0

    # Penalize if the smaller set is much smaller than the larger
    size_ratio = len(smaller) / len(larger) if larger else 0
    length_factor = 0.5 + 0.5 * size_ratio

    return containment * length_factor * 100


# ═══════════════════════════════════════════════════════════════
# Combined scoring engine
# ═══════════════════════════════════════════════════════════════

def _compute_match_score(
    name_a: str,
    name_b: str,
    idf: dict[str, float],
) -> float:
    """Compute a robust match score between two product names.

    Multi-signal fusion:
      1. token_sort_ratio — handles reordered words
      2. token_set_ratio — handles extra/missing words (with guard)
      3. plain ratio — basic Levenshtein
      4. IDF-weighted token overlap — distinctive words matter more
      5. Containment score — handles subset names
      6. Trigram similarity — resilient to OCR character errors
      7. Size compatibility penalty
    """
    tokens_a = _extract_significant_tokens(name_a)
    tokens_b = _extract_significant_tokens(name_b)

    # --- Fuzzy string scores ---
    sort_score = fuzz.token_sort_ratio(name_a, name_b)
    set_score = fuzz.token_set_ratio(name_a, name_b)
    plain_score = fuzz.ratio(name_a, name_b)

    # Guard token_set_ratio with softer threshold
    overlap = tokens_a & tokens_b
    if tokens_a and tokens_b:
        overlap_ratio_a = len(overlap) / len(tokens_a)
        overlap_ratio_b = len(overlap) / len(tokens_b)
        min_overlap = min(overlap_ratio_a, overlap_ratio_b)

        if min_overlap < 0.3:
            set_score = min(set_score, sort_score)
    else:
        set_score = 0

    # --- Token-based scores ---
    idf_score = _weighted_token_overlap(tokens_a, tokens_b, idf)
    contain_score = _containment_score(tokens_a, tokens_b)

    # --- Character-level score ---
    trigram_score = _trigram_similarity(name_a, name_b)

    # --- Combine: best of each signal family ---
    fuzzy_best = max(sort_score, set_score, plain_score)
    token_best = max(idf_score, contain_score)

    combined = (
        fuzzy_best * 0.50
        + token_best * 0.30
        + trigram_score * 0.20
    )

    # Convergence bonus: multiple independent signals agree
    strong_signals = sum(1 for s in [fuzzy_best, token_best, trigram_score] if s >= 60)
    if strong_signals >= 2:
        combined = combined * 1.10
    if strong_signals >= 3:
        combined = combined * 1.05

    combined = min(combined, 99.0)

    # Size penalty
    if not _size_compatible(name_a, name_b):
        combined = combined * 0.4

    return combined


# ═══════════════════════════════════════════════════════════════
# Main matching engine
# ═══════════════════════════════════════════════════════════════

async def match_invoice_items(
    invoice_id: int,
    db: AsyncSession,
) -> dict:
    """Run the matching engine on all items of an invoice.

    Returns a summary dict with match statistics and top candidates per item.
    """
    result = await db.execute(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id)
        .order_by(InvoiceItem.line_number)
    )
    items = result.scalars().all()

    if not items:
        return {"total": 0, "matched": 0, "unmatched": 0, "items": []}

    prod_result = await db.execute(
        select(Product).where(Product.is_active == True)  # noqa: E712
    )
    products = prod_result.scalars().all()

    barcode_map: dict[str, Product] = {}
    desc_map: dict[str, Product] = {}
    all_products: list[Product] = []

    for p in products:
        if p.barcode:
            barcode_map[p.barcode.strip()] = p
        desc_map[p.description.strip().lower()] = p
        all_products.append(p)

    # Pre-compute IDF for token weighting
    idf = _build_idf(all_products)

    matched_count = 0
    unmatched_count = 0
    item_results = []

    for item in items:
        match_result = _match_single_item(item, barcode_map, desc_map, all_products, idf)

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
            "candidates": match_result.get("candidates", []),
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
    idf: dict[str, float],
) -> dict:
    """Match a single invoice item against the product database.

    Always returns top candidates so the user can verify or override.
    """
    no_match = {
        "product_id": None,
        "matched": False,
        "confidence": None,
        "method": None,
        "product_name": None,
        "uom_mismatch": False,
        "candidates": [],
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
                "candidates": [{"product_id": product.id, "product_name": product.description,
                                "confidence": 1.0, "method": "barcode"}],
            }

        # --- Priority 2: Partial barcode match ---
        if len(barcode) >= 4:
            for db_barcode, product in barcode_map.items():
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
                        "candidates": [{"product_id": product.id, "product_name": product.description,
                                        "confidence": 0.9, "method": "barcode_partial"}],
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
            "candidates": [{"product_id": product.id, "product_name": product.description,
                            "confidence": 0.95, "method": "exact_name"}],
        }

    # Normalized comparison
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
                "candidates": [{"product_id": product.id, "product_name": product.description,
                                "confidence": 0.95, "method": "exact_name_normalized"}],
            }

    # --- Priority 4: Multi-signal fuzzy match with candidates ---
    if not all_products:
        return no_match

    scored: list[tuple[float, Product]] = []

    for product in all_products:
        prod_normalized = _normalize_text(product.description)
        score = _compute_match_score(name_normalized, prod_normalized, idf)

        if score >= FUZZY_THRESHOLD:
            scored.append((score, product))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:MAX_CANDIDATES]

    candidates = []
    for score, product in top:
        candidates.append({
            "product_id": product.id,
            "product_name": product.description,
            "confidence": round(score / 100, 2),
            "method": "fuzzy",
        })

    if top:
        best_score, best_product = top[0]
        confidence = Decimal(str(round(best_score / 100, 2)))
        auto_matched = float(confidence) >= AUTO_MATCH_THRESHOLD
        uom_mismatch = _check_uom_mismatch(item.extracted_uom, best_product.uom)

        logger.info(
            "Fuzzy match: '%s' → '%s' (score=%.1f, confidence=%s, auto=%s, candidates=%d)",
            name, best_product.description, best_score, confidence, auto_matched, len(candidates),
        )

        return {
            "product_id": best_product.id,
            "matched": auto_matched,
            "confidence": confidence,
            "method": "fuzzy",
            "product_name": best_product.description,
            "uom_mismatch": uom_mismatch,
            "candidates": candidates,
        }

    return no_match


# ═══════════════════════════════════════════════════════════════
# Suggestions endpoint helper
# ═══════════════════════════════════════════════════════════════

async def get_item_suggestions(
    item_id: int,
    db: AsyncSession,
    limit: int = 10,
) -> list[dict]:
    """Get top product suggestions for an invoice item.

    Re-runs the scoring engine for this item and returns top candidates.
    """
    item = await db.get(InvoiceItem, item_id)
    if not item or not item.extracted_name:
        return []

    prod_result = await db.execute(
        select(Product).where(Product.is_active == True)  # noqa: E712
    )
    products = prod_result.scalars().all()

    if not products:
        return []

    idf = _build_idf(products)
    name_normalized = _normalize_text(item.extracted_name)

    scored: list[tuple[float, Product]] = []
    for product in products:
        prod_normalized = _normalize_text(product.description)
        score = _compute_match_score(name_normalized, prod_normalized, idf)
        if score >= SUGGESTION_THRESHOLD * 100:
            scored.append((score, product))

    scored.sort(key=lambda x: x[0], reverse=True)

    suggestions = []
    for score, product in scored[:limit]:
        suggestions.append({
            "product_id": product.id,
            "product_name": product.description,
            "barcode": product.barcode,
            "uom": product.uom,
            "confidence": round(score / 100, 2),
        })

    return suggestions


# ═══════════════════════════════════════════════════════════════
# UOM mismatch detection
# ═══════════════════════════════════════════════════════════════

def _check_uom_mismatch(extracted_uom: str | None, product_uom: str | None) -> bool:
    """Check if there's a UOM mismatch between invoice and product."""
    if not extracted_uom or not product_uom:
        return False

    ext = extracted_uom.strip().upper()
    prod = product_uom.strip().upper()

    if ext == prod:
        return False

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
        ext_base = ext.split("-")[0].split("(")[0]
        prod_base = prod.split("-")[0].split("(")[0]
        if ext_base in group and prod_base in group:
            return False

    return True


# ═══════════════════════════════════════════════════════════════
# Manual match
# ═══════════════════════════════════════════════════════════════

async def manual_match_item(
    item_id: int,
    product_id: int,
    db: AsyncSession,
) -> InvoiceItem:
    """Manually match an invoice item to a product."""
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
