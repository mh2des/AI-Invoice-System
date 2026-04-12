"""Chat API — conversational AI assistant with persistent session history."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.models.chat_session import ChatSession, ChatMessage as ChatMessageModel
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


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    text: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    session_id: int | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: int


class SessionSummary(BaseModel):
    id: int
    title: str | None
    created_at: str
    updated_at: str
    message_count: int
    last_message: str | None


class SessionMessage(BaseModel):
    id: int
    role: str
    text: str
    created_at: str


class SessionDetail(BaseModel):
    id: int
    title: str | None
    created_at: str
    messages: list[SessionMessage]


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_or_create_session(
    db: AsyncSession,
    session_id: int | None,
    first_user_message: str,
) -> ChatSession:
    """Retrieve an existing session or create a new one."""
    if session_id is not None:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return session

    title = first_user_message[:80].strip() or "New Chat"
    session = ChatSession(title=title, message_count=0)
    db.add(session)
    await db.flush()
    return session


async def _save_messages(
    db: AsyncSession,
    session: ChatSession,
    user_text: str,
    assistant_text: str,
    image_refs: list[dict] | None = None,
) -> None:
    """Persist a user+assistant message pair and update session counters."""
    user_msg = ChatMessageModel(
        session_id=session.id,
        role="user",
        text=user_text,
        image_refs=image_refs or None,
    )
    assistant_msg = ChatMessageModel(
        session_id=session.id,
        role="assistant",
        text=assistant_text,
    )
    db.add_all([user_msg, assistant_msg])
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session.id)
        .values(
            message_count=ChatSession.message_count + 2,
            updated_at=func.now(),
        )
    )


# ── Chat endpoints ────────────────────────────────────────────────────────────

@router.post("/", response_model=ChatResponse)
async def chat_text(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a text-only message to the AI assistant. Auto-saves to a session."""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    session = await _get_or_create_session(db, body.session_id, body.message)

    try:
        reply = await chat_with_ai(
            message=body.message,
            image_data=None,
            conversation_history=[m.model_dump() for m in body.history],
            db=db,
        )
        await _save_messages(db, session, body.message, reply)
        await db.commit()
        return ChatResponse(reply=reply, session_id=session.id)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error("Chat error: %s", e)
        raise HTTPException(status_code=500, detail="AI assistant error. Please try again.")


@router.post("/with-image", response_model=ChatResponse)
async def chat_with_image(
    message: str = Form(...),
    history: str = Form(default="[]"),
    session_id: int | None = Form(default=None),
    files: list[UploadFile] = File(..., description="Receipt/invoice images"),
    db: AsyncSession = Depends(get_db),
):
    """Send a message with image attachments. Auto-saves to a session."""
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Parse history JSON
    try:
        history_list = json.loads(history)
    except Exception:
        history_list = []

    # Validate and read images
    image_data: list[tuple[bytes, str]] = []
    image_refs: list[dict] = []
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
        image_refs.append({"filename": f.filename, "content_type": f.content_type})

    session = await _get_or_create_session(db, session_id, message)

    try:
        reply = await chat_with_ai(
            message=message,
            image_data=image_data,
            conversation_history=history_list,
            db=db,
        )
        await _save_messages(db, session, message, reply, image_refs=image_refs)
        await db.commit()
        return ChatResponse(reply=reply, session_id=session.id)
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error("Chat with image error: %s", e)
        raise HTTPException(status_code=500, detail="AI assistant error. Please try again.")


# ── Session management endpoints ──────────────────────────────────────────────

@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """List all chat sessions ordered by most recently updated."""
    result = await db.execute(
        select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(100)
    )
    sessions = result.scalars().all()

    summaries = []
    for s in sessions:
        last_msg_result = await db.execute(
            select(ChatMessageModel.text)
            .where(
                ChatMessageModel.session_id == s.id,
                ChatMessageModel.role == "assistant",
            )
            .order_by(ChatMessageModel.created_at.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()
        preview = (last_msg[:100] + "…") if last_msg and len(last_msg) > 100 else last_msg

        summaries.append(
            SessionSummary(
                id=s.id,
                title=s.title,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
                message_count=s.message_count,
                last_message=preview,
            )
        )
    return summaries


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Get a session with all its messages."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    msgs_result = await db.execute(
        select(ChatMessageModel)
        .where(ChatMessageModel.session_id == session_id)
        .order_by(ChatMessageModel.created_at)
    )
    messages = msgs_result.scalars().all()

    return SessionDetail(
        id=session.id,
        title=session.title,
        created_at=session.created_at.isoformat(),
        messages=[
            SessionMessage(
                id=m.id,
                role=m.role,
                text=m.text,
                created_at=m.created_at.isoformat(),
            )
            for m in messages
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a chat session and all its messages."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    await db.delete(session)
    await db.commit()
