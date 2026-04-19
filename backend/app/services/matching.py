import logging
import math
import re
import time
import threading
from collections import Counter
from decimal import Decimal

from rapidfuzz import fuzz, process as rfprocess
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice_item import InvoiceItem
from app.models.product import Product

logger = logging.getLogger(__name__)

# ── Confidence thresholds ──
BARCODE_CONFIDENCE = Decimal("1.00")
BARCODE_PARTIAL_CONFIDENCE = Decimal("0.90")
EXACT_NAME_CONFIDENCE = Decimal("0.95")
FUZZY_THRESHOLD = 35           # minimum combined score to keep as candidate
AUTO_MATCH_THRESHOLD = 0.58    # above this → auto-matched
SUGGESTION_THRESHOLD = 0.30    # above this → shown as suggestion
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

    # Remove trailing pack-size patterns FIRST (before general multiplier removal)
    # Handles: "product 330 ml * 24", "product 500g * 12", "product 200ml*48", "product * 24"
    text = re.sub(r'\s*[*x×]\s*\d+\s*$', '', text)

    # Remove packaging multipliers in the middle: "1*50", "1x12", "3 x 4"
    text = re.sub(r'\b\d+\s*[*x×]\s*\d+\b', ' ', text)

    # Remove trailing count patterns: "24's", "x48", "x 12"
    text = re.sub(r"\d+'s\b", ' ', text)

    # Remove parenthesized content like (1*12), (500ML), (PROMO)
    text = re.sub(r'\([^)]*\)', ' ', text)

    # Remove common noise characters
    text = re.sub(r'[*#@!~`"\'{}[\]|\\]', ' ', text)

    # Remove standalone short codes that are likely article/stock codes (e.g., "AL505", "FS-001")
    # Only at start or end to avoid stripping from mid-name
    text = re.sub(r'^[a-z]{1,3}[-]?\d{3,}[a-z]?\s+', ' ', text)
    text = re.sub(r'\s+[a-z]{1,3}[-]?\d{3,}[a-z]?$', ' ', text)

    # Remove standalone pure numbers (pack counts, article numbers) but keep sizes like "500g"
    text = re.sub(r'\b\d+\b(?!\s*(?:ml|g|gm|kg|ltr|lt|l|oz|gram|liter|litre)\b)', ' ', text)

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


def _compute_trigrams(s: str) -> frozenset[str]:
    """Pre-compute character trigram set for a string."""
    n = 3
    if len(s) < n:
        return frozenset()
    return frozenset(s[i:i + n] for i in range(len(s) - n + 1))


def _trigram_similarity_fast(
    query_trigrams: frozenset[str],
    product_trigrams: frozenset[str],
) -> float:
    """Trigram Jaccard using pre-computed sets (0-100)."""
    if not query_trigrams or not product_trigrams:
        return 0.0
    overlap = query_trigrams & product_trigrams
    union = query_trigrams | product_trigrams
    return (len(overlap) / len(union)) * 100 if union else 0.0


# ═══════════════════════════════════════════════════════════════
# Token importance weighting (lightweight IDF)
# ═══════════════════════════════════════════════════════════════

def _build_idf_from_tokens(
    product_tokens: dict[int, frozenset[str]],
    doc_count: int,
) -> dict[str, float]:
    """Build IDF map from pre-computed token sets."""
    if doc_count == 0:
        return {}
    df: Counter = Counter()
    for tokens in product_tokens.values():
        for t in tokens:
            df[t] += 1
    return {
        token: math.log(doc_count / freq)
        for token, freq in df.items()
        if freq > 0
    }


# ═══════════════════════════════════════════════════════════════
# Product Index — pre-computed data structures cached in memory
# ═══════════════════════════════════════════════════════════════

_INDEX_TTL = 300  # seconds (5 minutes)
_cached_index: "_ProductIndex | None" = None
_index_lock = threading.Lock()


class _ProductIndex:
    """All pre-computed product data for fast matching.

    Built once, cached at module level, reused across requests.
    Avoids re-normalizing, re-tokenizing, and re-computing IDF for every call.
    """

    def __init__(self, products: list["Product"]):
        self.built_at = time.monotonic()
        self.product_count = len(products)

        self.barcode_map: dict[str, Product] = {}
        self.desc_map: dict[str, Product] = {}
        self.product_by_id: dict[int, Product] = {}
        self.norm_desc_map: dict[int, str] = {}
        self.norm_to_product: dict[str, Product] = {}  # normalized → product (O(1) lookup)
        self.prefilter_choices: dict[int, str] = {}
        self.product_tokens: dict[int, frozenset[str]] = {}
        self.product_trigrams: dict[int, frozenset[str]] = {}
        self.product_sizes: dict[int, tuple[float | None, str | None]] = {}

        for p in products:
            if p.barcode:
                self.barcode_map[p.barcode.strip()] = p
            self.desc_map[p.description.strip().lower()] = p
            self.product_by_id[p.id] = p

            nd = _normalize_text(p.description)
            self.norm_desc_map[p.id] = nd
            self.norm_to_product[nd] = p
            self.prefilter_choices[p.id] = nd
            self.product_tokens[p.id] = frozenset(_extract_significant_tokens(nd))
            self.product_trigrams[p.id] = _compute_trigrams(nd)
            self.product_sizes[p.id] = _extract_size(nd)

        self.idf = _build_idf_from_tokens(self.product_tokens, self.product_count)

    def is_stale(self) -> bool:
        return (time.monotonic() - self.built_at) > _INDEX_TTL


async def _get_or_build_index(db: AsyncSession) -> "_ProductIndex":
    """Return cached product index, rebuilding if stale or product count changed."""
    global _cached_index

    # Quick check without lock
    if _cached_index is not None and not _cached_index.is_stale():
        return _cached_index

    # Check if product count changed (fast DB query)
    count_result = await db.execute(
        select(sqlfunc.count()).select_from(Product).where(Product.is_active == True)  # noqa: E712
    )
    current_count = count_result.scalar() or 0

    with _index_lock:
        # Double-check after acquiring lock
        if (
            _cached_index is not None
            and not _cached_index.is_stale()
            and _cached_index.product_count == current_count
        ):
            return _cached_index

        # Rebuild
        prod_result = await db.execute(
            select(Product).where(Product.is_active == True)  # noqa: E712
        )
        products = prod_result.scalars().all()

        _cached_index = _ProductIndex(products)
        logger.info(
            "Product index rebuilt: %d products, IDF with %d tokens",
            _cached_index.product_count,
            len(_cached_index.idf),
        )
        return _cached_index


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
# Pre-filter: quickly shortlist candidates using rapidfuzz C code
# ═══════════════════════════════════════════════════════════════

# Number of candidates to pass through the fast pre-filter before full scoring
PREFILTER_LIMIT = 60


def _prefilter_candidates(
    query: str,
    choices: dict[int, str],
) -> list[int]:
    """Use rapidfuzz.process.extract for a fast C-level shortlist.

    Returns product IDs of the top PREFILTER_LIMIT candidates by token_sort_ratio.
    This avoids running the expensive multi-signal scorer on all 5000+ products.
    """
    if not choices:
        return []
    results = rfprocess.extract(
        query,
        choices,
        scorer=fuzz.token_sort_ratio,
        limit=PREFILTER_LIMIT,
        score_cutoff=25,  # very low — just eliminate total garbage
    )
    return [product_id for _, score, product_id in results]


# ═══════════════════════════════════════════════════════════════
# Combined scoring engine
# ═══════════════════════════════════════════════════════════════

def _compute_match_score(
    name_a: str,
    name_b: str,
    idf: dict[str, float],
    *,
    tokens_a: frozenset[str] | None = None,
    tokens_b: frozenset[str] | None = None,
    trigrams_a: frozenset[str] | None = None,
    trigrams_b: frozenset[str] | None = None,
    size_a: tuple[float | None, str | None] | None = None,
    size_b: tuple[float | None, str | None] | None = None,
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

    Accepts optional pre-computed tokens/trigrams/sizes to avoid redundant work.
    """
    t_a = set(tokens_a) if tokens_a is not None else _extract_significant_tokens(name_a)
    t_b = set(tokens_b) if tokens_b is not None else _extract_significant_tokens(name_b)

    # --- Fuzzy string scores (C-level, fast) ---
    sort_score = fuzz.token_sort_ratio(name_a, name_b)
    set_score = fuzz.token_set_ratio(name_a, name_b)
    plain_score = fuzz.ratio(name_a, name_b)

    # Guard token_set_ratio with softer threshold
    overlap = t_a & t_b
    if t_a and t_b:
        overlap_ratio_a = len(overlap) / len(t_a)
        overlap_ratio_b = len(overlap) / len(t_b)
        min_overlap = min(overlap_ratio_a, overlap_ratio_b)

        if min_overlap < 0.3:
            set_score = min(set_score, sort_score)
    else:
        set_score = 0

    # --- Token-based scores ---
    idf_score = _weighted_token_overlap(t_a, t_b, idf)
    contain_score = _containment_score(t_a, t_b)

    # --- Character-level score (use pre-computed if available) ---
    if trigrams_a is not None and trigrams_b is not None:
        trigram_score = _trigram_similarity_fast(trigrams_a, trigrams_b)
    else:
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

    # Size penalty (use pre-computed if available)
    if size_a is not None and size_b is not None:
        s_a, cat_a = size_a
        s_b, cat_b = size_b
        if s_a is not None and s_b is not None and cat_a == cat_b:
            if s_a == 0 or s_b == 0:
                if s_a != s_b:
                    combined = combined * 0.4
            else:
                ratio = max(s_a, s_b) / min(s_a, s_b)
                if ratio > 1.2:
                    combined = combined * 0.4
    else:
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

    Uses cached ProductIndex for fast lookups. Rebuilds index only if stale.
    """
    result = await db.execute(
        select(InvoiceItem).where(InvoiceItem.invoice_id == invoice_id)
        .order_by(InvoiceItem.line_number)
    )
    items = result.scalars().all()

    if not items:
        return {"total": 0, "matched": 0, "unmatched": 0, "items": []}

    idx = await _get_or_build_index(db)

    matched_count = 0
    unmatched_count = 0
    item_results = []

    for item in items:
        match_result = _match_single_item(item, idx)

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
    idx: _ProductIndex,
) -> dict:
    """Match a single invoice item using the cached ProductIndex.

    Pre-filter → full multi-signal scoring with pre-computed data.
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
        if barcode in idx.barcode_map:
            product = idx.barcode_map[barcode]
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
            for db_barcode, product in idx.barcode_map.items():
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

    # --- Priority 3a: Exact description match (case-insensitive, O(1)) ---
    if name_lower in idx.desc_map:
        product = idx.desc_map[name_lower]
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

    # --- Priority 3b: Normalized exact match (O(1) dict lookup) ---
    if name_normalized in idx.norm_to_product:
        product = idx.norm_to_product[name_normalized]
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

    # --- Priority 4: Pre-filtered multi-signal fuzzy match ---
    if not idx.prefilter_choices:
        return no_match

    # Pre-compute query-side data once per item
    query_tokens = frozenset(_extract_significant_tokens(name_normalized))
    query_trigrams = _compute_trigrams(name_normalized)
    query_size = _extract_size(name_normalized)

    # Fast C-level pre-filter: shortlist ~60 candidates
    candidate_ids = _prefilter_candidates(name_normalized, idx.prefilter_choices)

    scored: list[tuple[float, Product]] = []

    for pid in candidate_ids:
        score = _compute_match_score(
            name_normalized,
            idx.norm_desc_map[pid],
            idx.idf,
            tokens_a=query_tokens,
            tokens_b=idx.product_tokens[pid],
            trigrams_a=query_trigrams,
            trigrams_b=idx.product_trigrams[pid],
            size_a=query_size,
            size_b=idx.product_sizes[pid],
        )
        if score >= FUZZY_THRESHOLD:
            scored.append((score, idx.product_by_id[pid]))

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
    """Get top product suggestions for a single invoice item.

    Uses cached ProductIndex — no redundant rebuilds.
    """
    item = await db.get(InvoiceItem, item_id)
    if not item or not item.extracted_name:
        return []

    idx = await _get_or_build_index(db)
    return _score_suggestions(item.extracted_name, idx, limit)


async def get_invoice_suggestions(
    invoice_id: int,
    db: AsyncSession,
    limit: int = 10,
) -> dict[int, list[dict]]:
    """Get suggestions for ALL unmatched items of an invoice in one call.

    Returns {item_id: [suggestions...]} — eliminates N separate API calls.
    """
    result = await db.execute(
        select(InvoiceItem).where(
            InvoiceItem.invoice_id == invoice_id,
            InvoiceItem.matched == False,  # noqa: E712
        )
    )
    unmatched_items = result.scalars().all()

    if not unmatched_items:
        return {}

    idx = await _get_or_build_index(db)
    suggestions_map: dict[int, list[dict]] = {}

    for item in unmatched_items:
        if not item.extracted_name:
            suggestions_map[item.id] = []
            continue
        suggestions_map[item.id] = _score_suggestions(item.extracted_name, idx, limit)

    return suggestions_map


def _score_suggestions(
    extracted_name: str,
    idx: _ProductIndex,
    limit: int,
) -> list[dict]:
    """Score and rank product suggestions using the cached index."""
    name_normalized = _normalize_text(extracted_name)
    query_tokens = frozenset(_extract_significant_tokens(name_normalized))
    query_trigrams = _compute_trigrams(name_normalized)
    query_size = _extract_size(name_normalized)

    candidate_ids = _prefilter_candidates(name_normalized, idx.prefilter_choices)

    scored: list[tuple[float, Product]] = []
    for pid in candidate_ids:
        score = _compute_match_score(
            name_normalized,
            idx.norm_desc_map[pid],
            idx.idf,
            tokens_a=query_tokens,
            tokens_b=idx.product_tokens[pid],
            trigrams_a=query_trigrams,
            trigrams_b=idx.product_trigrams[pid],
            size_a=query_size,
            size_b=idx.product_sizes[pid],
        )
        if score >= SUGGESTION_THRESHOLD * 100:
            scored.append((score, idx.product_by_id[pid]))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {
            "product_id": product.id,
            "product_name": product.description,
            "barcode": product.barcode,
            "uom": product.uom,
            "confidence": round(score / 100, 2),
        }
        for score, product in scored[:limit]
    ]


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
