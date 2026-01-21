from pydantic import BaseModel, EmailStr, Field, field_validator


class ResetPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordConfirm(BaseModel):
    email: EmailStr
    otp_code: str
    new_password: str = Field(..., min_length=8, max_length=1024)

    @field_validator("new_password")
    def new_password_byte_length(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 1024:
            raise ValueError("new_password cannot be longer than 1024 bytes; choose a shorter password")
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=1024)

    @field_validator("new_password")
    def change_new_password_byte_length(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 1024:
            raise ValueError("new_password cannot be longer than 1024 bytes; choose a shorter password")
        return v
