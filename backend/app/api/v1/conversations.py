import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.v1.auth import get_current_user
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.logging import logger
from app.db.session import get_db
from app.models.citation import Citation
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.conversation import (
    CitationResponse,
    ConversationCreate,
    ConversationResponse,
    MessageResponse,
)

router = APIRouter(tags=["conversations"])


async def _verify_workspace_access(
    workspace_id: uuid.UUID, user: User, db: AsyncSession
) -> Workspace:
    """Verifies user ownership of a workspace."""
    query = select(Workspace).where(Workspace.id == workspace_id)
    res = await db.execute(query)
    workspace = res.scalar_one_or_none()
    if not workspace:
        raise NotFoundError(message="Workspace not found")
    if workspace.user_id != user.id:
        raise PermissionDeniedError(message="Access denied to this workspace")
    return workspace


@router.post(
    "/workspaces/{workspace_id}/conversations",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    workspace_id: uuid.UUID,
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationResponse:
    """Creates a new conversation in a workspace."""
    await _verify_workspace_access(workspace_id, current_user, db)

    conversation = Conversation(
        title=payload.title or "New Conversation",
        workspace_id=workspace_id,
        user_id=current_user.id,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    logger.info(f"Conversation created: {conversation.id} in workspace {workspace_id}")
    return ConversationResponse.model_validate(conversation)


@router.get(
    "/workspaces/{workspace_id}/conversations",
    response_model=list[ConversationResponse],
)
async def list_conversations(
    workspace_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationResponse]:
    """Lists all conversations for a workspace."""
    await _verify_workspace_access(workspace_id, current_user, db)

    query = (
        select(Conversation)
        .where(Conversation.workspace_id == workspace_id)
        .order_by(Conversation.updated_at.desc())
    )
    res = await db.execute(query)
    conversations = res.scalars().all()
    return [ConversationResponse.model_validate(c) for c in conversations]


@router.get(
    "/conversations/{conversation_id}/messages", response_model=list[MessageResponse]
)
async def list_conversation_messages(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MessageResponse]:
    """Retrieves full message history for a conversation along with citations."""
    # Verify conversation ownership
    query = select(Conversation).where(Conversation.id == conversation_id)
    res = await db.execute(query)
    conversation = res.scalar_one_or_none()

    if not conversation:
        raise NotFoundError(message="Conversation not found")
    if conversation.user_id != current_user.id:
        raise PermissionDeniedError(message="Access denied to this conversation")

    # Fetch messages
    msg_query = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    msg_res = await db.execute(msg_query)
    messages = msg_res.scalars().all()

    # Fetch citations for all assistant messages
    msg_ids = [m.id for m in messages if m.role == "assistant"]
    citations_by_msg: dict[uuid.UUID, list[Citation]] = {m_id: [] for m_id in msg_ids}

    if msg_ids:
        cit_query = select(Citation).where(Citation.message_id.in_(msg_ids))
        cit_res = await db.execute(cit_query)
        citations = cit_res.scalars().all()
        for cit in citations:
            citations_by_msg[cit.message_id].append(cit)

    # Format response
    response_list = []
    for msg in messages:
        m_resp = MessageResponse.model_validate(msg)
        if msg.role == "assistant" and msg.id in citations_by_msg:
            m_resp.citations = [
                CitationResponse.model_validate(c) for c in citations_by_msg[msg.id]
            ]
        response_list.append(m_resp)

    return response_list


@router.delete(
    "/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes a conversation and its message logs."""
    query = select(Conversation).where(Conversation.id == conversation_id)
    res = await db.execute(query)
    conversation = res.scalar_one_or_none()

    if not conversation:
        raise NotFoundError(message="Conversation not found")
    if conversation.user_id != current_user.id:
        raise PermissionDeniedError(message="Access denied to this conversation")

    await db.delete(conversation)
    await db.commit()
    logger.info(f"Deleted conversation {conversation_id}")
