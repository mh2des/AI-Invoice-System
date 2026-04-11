"""Chat service — conversational AI assistant powered by Gemini.

Provides context-aware responses using invoice data, products, and suppliers
from the database. Supports image attachments (receipts) in conversation.
Uses the primary model with automatic fallback to a stable model.
"""

import json
import logging

from google import genai
from google.genai import types
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.product import Product
from app.models.supplier import Supplier

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an AI accounting assistant for a small business invoice processing system.

You help users with:
- Analyzing receipt/invoice images they send you
- Answering questions about their invoices, products, suppliers, and spending
- Providing summaries and insights from their data
- Guiding them on how to use the system

You have access to the following database context (provided below).
When the user sends an image, analyze it as a receipt/invoice and extract key information.
Be concise, professional, and helpful. Use the database context to give rich answers.
Format currency amounts with 2 decimal places.
If you're not sure about something, say so.

DATABASE CONTEXT:
{db_context}
"""


async def _build_db_context(db: AsyncSession) -> str:
    """Build a summary of the database state for the system prompt."""
    # Invoice stats
    total_invoices = (await db.execute(select(func.count(Invoice.id)))).scalar() or 0
    done_invoices = (
        await db.execute(
            select(func.count(Invoice.id)).where(Invoice.status == "done")
        )
    ).scalar() or 0

    # Recent invoices
    recent_result = await db.execute(
        select(Invoice).order_by(Invoice.created_at.desc()).limit(10)
    )
    recent_invoices = recent_result.scalars().all()

    # Suppliers
    supplier_result = await db.execute(select(Supplier).limit(50))
    suppliers = supplier_result.scalars().all()

    # Product count
    product_count = (await db.execute(select(func.count(Product.id)))).scalar() or 0

    # Match stats
    total_items = (await db.execute(select(func.count(InvoiceItem.id)))).scalar() or 0
    matched_items = (
        await db.execute(
            select(func.count(InvoiceItem.id)).where(InvoiceItem.matched == True)  # noqa: E712
        )
    ).scalar() or 0

    lines = [
        f"Total invoices: {total_invoices} ({done_invoices} processed)",
        f"Total products in DB: {product_count}",
        f"Total items extracted: {total_items}, matched: {matched_items}",
        f"Suppliers ({len(suppliers)}): {', '.join(s.name for s in suppliers) or 'None'}",
        "",
        "Recent invoices:",
    ]

    for inv in recent_invoices:
        lines.append(
            f"  - Invoice #{inv.id} | {inv.invoice_number or 'No number'} | "
            f"Status: {inv.status} | Total: {inv.grand_total or '?'} {inv.currency} | "
            f"Date: {inv.invoice_date or '?'}"
        )

    return "\n".join(lines)


async def chat_with_ai(
    message: str,
    image_data: list[tuple[bytes, str]] | None,
    conversation_history: list[dict],
    db: AsyncSession,
) -> str:
    """Send a message (with optional images) to Gemini and get a response.

    Args:
        message: The user's text message.
        image_data: Optional list of (bytes, mime_type) for attached images.
        conversation_history: List of previous messages [{role, text}].
        db: Database session for context.

    Returns:
        The AI assistant's response text.
    """
    settings = get_settings()

    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_gemini_api_key_here":
        raise ValueError("GEMINI_API_KEY is not configured.")

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Build database context
    db_context = await _build_db_context(db)
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
        "Chat request: %d history messages, %d images, message length: %d",
        len(conversation_history),
        len(image_data) if image_data else 0,
        len(message),
    )

    # Model cascade: try primary, then fallback
    models_to_try = [settings.GEMINI_PRIMARY_MODEL, settings.GEMINI_FALLBACK_MODEL]
    response = None
    last_error: Exception | None = None

    for model_index, model_name in enumerate(models_to_try):
        is_fallback = model_index > 0

        if is_fallback:
            logger.warning(
                "Primary chat model failed. Falling back to %s", model_name
            )

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                ),
            )
            logger.info("Chat responded via %s", model_name)
            break
        except Exception as e:
            last_error = e
            logger.error("Chat model %s failed: %s", model_name, e)

    if response is None:
        raise ValueError(
            f"Chat failed with all models: {last_error}"
        )

    reply = response.text
    logger.info("Chat response: %d chars", len(reply))
    return reply
