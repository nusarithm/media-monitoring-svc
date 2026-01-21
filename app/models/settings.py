from pydantic import BaseModel, Field, EmailStr
from typing import Optional


class ProfileUpdate(BaseModel):
    """Profile update model"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    email: Optional[EmailStr] = None


class UserCreate(BaseModel):
    """Create user for workspace"""
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    role_id: Optional[int] = None


class UserResponse(BaseModel):
    """User response model"""
    id: int
    name: Optional[str]
    email: str
    is_active: bool
    created_at: str
    workspace_id: Optional[int]
    role_id: Optional[int]
