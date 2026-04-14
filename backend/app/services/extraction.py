import asyncio
import json
import logging
from decimal import Decimal, InvalidOperation
from datetime import date

from google import genai
from google.genai import types

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds

EXTRACTION_PROMPT = """You are a professional invoice data extraction assistant.
Extract all data from this supplier invoice image(s).

The invoice may contain text in English, Arabic (العربية), Chinese (中文), or Malay.
Translate all product names to English in the output.

Return ONLY valid JSON, no markdown, no preamble.

{
  "invoice_number": "string or null",
  "supplier_name": "string or null",
  "date": "YYYY-MM-DD or null",
  "payment_terms": "string or null",
  "currency": "MYR",
  "items": [
    {
      "item_name": "string",
      "barcode": "string or null",
      "quantity": number,
      "uom": "string (e.g. CTN, BOX, PCS, UNIT, PAKET)",
      "unit_price": number,
      "discount_percent": number or null,
      "total": number
    }
  ],
  "subtotal": number or null,
  "discount_total": number or null,
  "grand_total": number
}

Rules:
- If multiple pages, combine ALL items into one array.
- If a field is not visible or illegible, use null.
- For handwritten invoices, do your best — mark uncertain values with a trailing "?" in item_name.
- UOM must be extracted exactly as shown (CTN, BOX, PCS, etc.)
- Discount: if a line item shows a discount percentage, capture it.
- Grand total: the final amount after all discounts."""

def _safe_decimal(value) -> Decimal | None:
    """Convert a value to Decimal safely, returning None on failure."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _safe_date(value: str | None) -> date | None:
    """Parse a YYYY-MM-DD string to a date object."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _build_image_parts(images: list[tuple[bytes, str]]) -> list[types.Part]:
    """Build Gemini content parts from image bytes.

    Args:
        images: List of (image_bytes, mime_type) tuples.
    """
    parts = []
    for image_bytes, mime_type in images:
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
    return parts


def _build_pdf_part(pdf_bytes: bytes) -> types.Part:
    """Build a Gemini content part from PDF bytes."""
    return types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")


async def extract_invoice_data(
    files: list[tuple[bytes, str]],
) -> dict:
    """Extract invoice data from uploaded images or PDF using Gemini.

    Uses the primary model with automatic fallback to a stable model.
    Supports multiple API keys for rotation when one is rate-limited/expired.

    Args:
        files: List of (file_bytes, mime_type) tuples.

    Returns:
        Dict with raw Gemini extraction result plus parsed fields.
    """
    settings = get_settings()

    # Collect all valid API keys
    api_keys = [
        k for k in [settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_2]
        if k and k not in ("", "your_gemini_api_key_here")
    ]
    if not api_keys:
        raise ValueError("GEMINI_API_KEY is not configured. Set it in .env file.")

    # Build content parts: prompt text + all file parts
    content_parts: list[types.Part] = []

    for file_bytes, mime_type in files:
        if mime_type == "application/pdf":
            content_parts.append(_build_pdf_part(file_bytes))
        else:
            content_parts.append(
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
            )

    # Add the prompt as the last part
    content_parts.append(types.Part.from_text(text=EXTRACTION_PROMPT))

    # Model cascade with key rotation
    models_to_try = [settings.GEMINI_PRIMARY_MODEL, settings.GEMINI_FALLBACK_MODEL]
    response = None
    last_error: Exception | None = None

    for key_index, api_key in enumerate(api_keys):
        client = genai.Client(api_key=api_key)
        key_label = f"key_{key_index + 1}"

        for model_index, model_name in enumerate(models_to_try):
            is_primary = model_index == 0

            logger.info(
                "Sending %d file(s) to %s [%s] for extraction",
                len(files), model_name, key_label,
            )

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    # Gemini 3.x models use thinking_level; 2.x models don't.
                    thinking = (
                        types.ThinkingConfig(thinking_level="MEDIUM")
                        if is_primary
                        else None
                    )
                    response = client.models.generate_content(
                        model=model_name,
                        contents=content_parts,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1,
                            thinking_config=thinking,
                        ),
                    )
                    logger.info(
                        "Extraction succeeded with %s [%s] (attempt %d/%d)",
                        model_name, key_label, attempt, MAX_RETRIES,
                    )
                    break
                except Exception as e:
                    last_error = e
                    err_msg = str(e).lower()
                    is_auth_error = "401" in err_msg or "unauthenticated" in err_msg

                    if is_auth_error:
                        logger.error(
                            "API %s is invalid/expired for %s: %s",
                            key_label, model_name, e,
                        )
                        break  # skip retries, try next key

                    if attempt < MAX_RETRIES:
                        delay = RETRY_BASE_DELAY ** attempt
                        logger.warning(
                            "%s [%s] extraction failed (attempt %d/%d): %s — retrying in %ds",
                            model_name, key_label, attempt, MAX_RETRIES, e, delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "%s [%s] extraction failed after %d attempts: %s",
                            model_name, key_label, MAX_RETRIES, e,
                        )

            # If we got a response, stop entirely
            if response is not None:
                break

            # If auth error, skip remaining models for this key
            if last_error and "401" in str(last_error).lower():
                break

        # If we got a response, stop trying more keys
        if response is not None:
            break

    # If no key+model succeeded, raise the last error
    if response is None:
        raise ValueError(
            f"Gemini extraction failed with all models and API keys: {last_error}"
        )

    # Parse the JSON response
    raw_text = response.text
    logger.info("Gemini response received (%d chars)", len(raw_text))

    try:
        raw_data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Gemini JSON response: %s\nRaw: %s", e, raw_text[:500])
        raise ValueError(f"Gemini returned invalid JSON: {e}") from e

    # Parse into structured result
    parsed = parse_extraction_result(raw_data)
    parsed["raw_json"] = raw_data

    return parsed


def parse_extraction_result(raw_data: dict) -> dict:
    """Parse raw Gemini JSON into structured fields for database storage.

    Returns:
        Dict with keys: invoice_number, supplier_name, invoice_date,
        payment_terms, currency, subtotal, discount_total, grand_total, items
    """
    items = []
    for i, item in enumerate(raw_data.get("items", []), start=1):
        items.append(
            {
                "line_number": i,
                "extracted_name": item.get("item_name"),
                "extracted_barcode": item.get("barcode"),
                "extracted_qty": _safe_decimal(item.get("quantity")),
                "extracted_uom": item.get("uom"),
                "extracted_unit_price": _safe_decimal(item.get("unit_price")),
                "extracted_discount": _safe_decimal(item.get("discount_percent")),
                "extracted_total": _safe_decimal(item.get("total")),
            }
        )

    return {
        "invoice_number": raw_data.get("invoice_number"),
        "supplier_name": raw_data.get("supplier_name"),
        "invoice_date": _safe_date(raw_data.get("date")),
        "payment_terms": raw_data.get("payment_terms"),
        "currency": raw_data.get("currency", "MYR"),
        "subtotal": _safe_decimal(raw_data.get("subtotal")),
        "discount_total": _safe_decimal(raw_data.get("discount_total")),
        "grand_total": _safe_decimal(raw_data.get("grand_total")),
        "items": items,
    }
