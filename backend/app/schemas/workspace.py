import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkspaceBase(BaseModel):
    """Shared Workspace properties"""

    name: str


class WorkspaceCreate(WorkspaceBase):
    """Schema for creating a new Workspace"""

    pass


class WorkspaceUpdate(BaseModel):
    """Schema for updating a Workspace"""

    name: str | None = None


class WorkspaceResponse(WorkspaceBase):
    """Schema for returning Workspace data"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
