from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    email: str = Field(..., description="User email address")
    full_name: Optional[str] = None


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    is_active: bool
    is_super_admin: bool
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    email: str = Field(..., description="Super admin email address")
    password: str = Field(..., description="Super admin password")


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
