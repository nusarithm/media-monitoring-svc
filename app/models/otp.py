from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerify(BaseModel):
    email: EmailStr
    otp_code: str


class OTPResponse(BaseModel):
    message: str
    email: str


class OTPInDB(BaseModel):
    id: int
    user_id: int
    otp_code: str
    expires_at: datetime
    is_used: bool
    verified_at: Optional[datetime] = None
    created_at: datetime
