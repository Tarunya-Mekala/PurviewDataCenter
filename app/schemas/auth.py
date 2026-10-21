from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    UPLOADER = "uploader"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class UserBase(BaseModel):
    email: str = Field(..., description="User email address")
    full_name: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, description="User password")
    role: UserRole = Field(default=UserRole.VIEWER, description="Assigned role: super_admin, admin, uploader, reviewer, viewer")


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6)


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    is_active: bool
    is_super_admin: bool
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    total: int
    items: List[UserResponse]


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class TokenPayload(BaseModel):
    sub: str
    email: str
    role: str
    is_super_admin: bool
