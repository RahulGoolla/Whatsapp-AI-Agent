import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    """Shared User properties"""

    email: EmailStr
    first_name: str | None = None
    last_name: str | None = None
    profile_image_url: str | None = None


class UserCreate(UserBase):
    """Schema used during Just-In-Time (JIT) user registration"""

    clerk_id: str


class UserUpdate(BaseModel):
    """Schema used for updating user profiles"""

    first_name: str | None = None
    last_name: str | None = None
    profile_image_url: str | None = None


class UserResponse(UserBase):
    """Schema for returning user records from the API"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    clerk_id: str
    created_at: datetime
    updated_at: datetime
