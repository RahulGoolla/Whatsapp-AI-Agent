import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationCreate(BaseModel):
    """Schema for initializing a new chat conversation"""

    title: str | None = "New Conversation"


class ConversationResponse(BaseModel):
    """Schema for returning Conversation details"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CitationResponse(BaseModel):
    """Schema for returning message source citations"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text_snippet: str
    page_number: int | None = None
    score: float | None = None
    document_id: uuid.UUID
    created_at: datetime


class MessageResponse(BaseModel):
    """Schema for returning message history logs"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    conversation_id: uuid.UUID
    created_at: datetime
    citations: list[CitationResponse] = []


class ChatStreamRequest(BaseModel):
    """Schema for triggering a RAG chat stream request"""

    conversation_id: uuid.UUID | None = None
    message: str
    document_id: uuid.UUID | None = None
