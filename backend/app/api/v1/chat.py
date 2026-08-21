import json
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.v1.auth import get_current_user
from app.core.exceptions import NotFoundError
from app.core.logging import logger
from app.db.session import AsyncSessionLocal, get_db
from app.models.citation import Citation
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.conversation import ChatStreamRequest
from app.services.rag import execute_rag_stream

router = APIRouter(tags=["chat"])


async def _resolve_workspace(
    workspace_id: uuid.UUID, user: User, db: AsyncSession
) -> Workspace:
    """Verifies or resolves workspace."""
    query = select(Workspace).where(Workspace.id == workspace_id)
    res = await db.execute(query)
    workspace = res.scalar_one_or_none()
    if not workspace:
        raise NotFoundError(message="Workspace not found")
    return workspace


async def _resolve_conversation(
    workspace_id: uuid.UUID,
    payload: ChatStreamRequest,
    user: User,
    db: AsyncSession,
) -> Conversation:
    """Resolves an existing conversation or auto-creates a new one."""
    if payload.conversation_id:
        conv_query = select(Conversation).where(
            Conversation.id == payload.conversation_id
        )
        conv_res = await db.execute(conv_query)
        conversation = conv_res.scalar_one_or_none()
        if conversation:
            return conversation

    title_snippet = payload.message[:35] + ("..." if len(payload.message) > 35 else "")
    conversation = Conversation(
        title=title_snippet,
        workspace_id=workspace_id,
        user_id=user.id,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def _persist_assistant_response(
    conversation_id: uuid.UUID,
    full_response_text: str,
    citations_list: list[dict],
) -> uuid.UUID:
    """Persists assistant response message and citations to database."""
    async with AsyncSessionLocal() as async_db:
        try:
            assistant_msg = Message(
                role="assistant",
                content=full_response_text,
                conversation_id=conversation_id,
            )
            async_db.add(assistant_msg)
            await async_db.commit()
            await async_db.refresh(assistant_msg)

            for cit in citations_list:
                doc_id_val = cit.get("document_id")
                try:
                    doc_uuid = uuid.UUID(doc_id_val) if doc_id_val else None
                except Exception:
                    doc_uuid = None

                if doc_uuid:
                    citation_record = Citation(
                        text_snippet=cit.get("text_snippet", cit.get("filename", "")),
                        page_number=cit.get("page"),
                        score=cit.get("score"),
                        message_id=assistant_msg.id,
                        document_id=doc_uuid,
                    )
                    async_db.add(citation_record)

            await async_db.commit()
            return assistant_msg.id
        except Exception as ex:
            logger.exception(f"Failed to persist assistant message response: {ex}")
            await async_db.rollback()
            raise


@router.post("/workspaces/{workspace_id}/chat/stream")
async def chat_stream(
    workspace_id: uuid.UUID,
    payload: ChatStreamRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Server-Sent Events (SSE) streaming RAG chat controller.
    Streams AI tokens while preserving message history and citation records.
    """
    await _resolve_workspace(workspace_id, current_user, db)
    conversation = await _resolve_conversation(workspace_id, payload, current_user, db)

    # Fetch previous message history
    hist_query = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .limit(10)
    )
    hist_res = await db.execute(hist_query)
    history_records = hist_res.scalars().all()

    messages_history = [
        {"role": msg.role, "content": msg.content} for msg in history_records
    ]
    messages_history.append({"role": "user", "content": payload.message})

    # Save user message to database
    user_msg = Message(
        role="user",
        content=payload.message,
        conversation_id=conversation.id,
    )
    db.add(user_msg)
    await db.commit()

    # Invoke RAG engine
    citations_list, token_stream, meta = await execute_rag_stream(
        workspace_id=workspace_id,
        query_text=payload.message,
        messages=messages_history,
        db=db,
        document_id=payload.document_id,
    )

    async def sse_event_generator() -> AsyncGenerator[str, None]:
        full_text_acc = []

        metadata_event = {
            "type": "metadata",
            "conversation_id": str(conversation.id),
            "citations": citations_list,
            "is_escalated": meta.get("is_escalated", False),
            "escalation_reason": meta.get("escalation_reason"),
        }
        yield f"data: {json.dumps(metadata_event)}\n\n"

        try:
            async for token in token_stream:
                full_text_acc.append(token)
                token_event = {"type": "token", "content": token}
                yield f"data: {json.dumps(token_event)}\n\n"
        except Exception as e:
            logger.error(f"Error during SSE token streaming: {e}")
            error_event = {
                "type": "error",
                "message": "An error occurred generating response.",
            }
            yield f"data: {json.dumps(error_event)}\n\n"
            return

        full_response_text = "".join(full_text_acc)

        try:
            msg_id = await _persist_assistant_response(
                conversation.id, full_response_text, citations_list
            )
            done_event = {
                "type": "done",
                "conversation_id": str(conversation.id),
                "message_id": str(msg_id),
            }
            yield f"data: {json.dumps(done_event)}\n\n"
        except Exception:
            pass

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")
