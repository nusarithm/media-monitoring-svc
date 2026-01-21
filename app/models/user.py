from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=1024)

    @field_validator("password")
    def password_byte_length(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 1024:
            raise ValueError("password cannot be longer than 1024 bytes; choose a shorter password")
        return v
    

class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    workspace_id: Optional[int] = None
    role_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class UserInDB(UserBase):
    id: int
    password: str
    is_active: bool
    created_at: datetime
    workspace_id: Optional[int] = None
    role_id: Optional[int] = None
