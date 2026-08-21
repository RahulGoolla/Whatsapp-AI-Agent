import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    """Schema for returning Document metadata and ingestion state"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_size: int
    mime_type: str | None = None
    status: str
    error_message: str | None = None
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class DocumentStatusResponse(BaseModel):
    """Schema for querying real-time document ingestion status"""

    id: uuid.UUID
    status: str
    error_message: str | None = None
