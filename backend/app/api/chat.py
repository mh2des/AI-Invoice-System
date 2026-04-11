"""Chat API endpoint — conversational AI assistant."""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.services.chat import chat_with_ai

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/tiff",
    "application/pdf",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    text: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str


@router.post("/", response_model=ChatResponse)
async def chat_text(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a text-only message to the AI assistant."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        reply = await chat_with_ai(
            message=body.message,
            image_data=None,
            conversation_history=[m.model_dump() for m in body.history],
            db=db,
        )
        return ChatResponse(reply=reply)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail="AI assistant error. Please try again.")


@router.post("/with-image", response_model=ChatResponse)
async def chat_with_image(
    message: str = Form(...),
    history: str = Form(default="[]"),
    files: list[UploadFile] = File(..., description="Receipt/invoice images"),
    db: AsyncSession = Depends(get_db),
):
    """Send a message with image attachments to the AI assistant."""
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Parse history JSON
    try:
        import json
        history_list = json.loads(history)
    except Exception:
        history_list = []

    # Validate and read images
    image_data: list[tuple[bytes, str]] = []
    for f in files:
        if f.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {f.content_type}",
            )
        content = await f.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {f.filename} exceeds 20MB limit",
            )
        image_data.append((content, f.content_type))

    try:
        reply = await chat_with_ai(
            message=message,
            image_data=image_data,
            conversation_history=history_list,
            db=db,
        )
        return ChatResponse(reply=reply)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Chat with image error: %s", e)
        raise HTTPException(status_code=500, detail="AI assistant error. Please try again.")
