from fastapi import APIRouter, HTTPException, status, Depends
from app.models.user import UserCreate, UserLogin, UserResponse
from app.models.token import Token, RefreshTokenRequest
from app.models.otp import OTPRequest, OTPVerify, OTPResponse
from app.models.password import ResetPasswordRequest, ResetPasswordConfirm
from app.services.auth_service import auth_service
from app.api.dependencies import get_current_active_user


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """
    Register a new user and send OTP verification email
    
    - **email**: Valid email address
    - **password**: Minimum 8 characters
    - **name**: Optional full name
    - **phone**: Optional phone number
    """
    return await auth_service.register(user_data)


@router.post("/verify-email", response_model=Token)
async def verify_email(otp_data: OTPVerify):
    """
    Verify email with OTP code and activate account
    
    - **email**: User's email address
    - **otp_code**: 6-digit OTP code from email
    """
    return await auth_service.verify_email(otp_data.email, otp_data.otp_code)


@router.post("/resend-otp", response_model=dict)
async def resend_otp(request: OTPRequest):
    """
    Resend OTP verification code to email
    
    - **email**: User's email address
    """
    return await auth_service.resend_otp(request.email)


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """
    Login with email and password
    
    - **email**: User's email address
    - **password**: User's password
    
    Returns access token and refresh token
    """
    return await auth_service.login(credentials)


@router.post("/refresh", response_model=Token)
async def refresh_token(request: RefreshTokenRequest):
    """
    Refresh access token using refresh token
    
    - **refresh_token**: Valid refresh token
    """
    return await auth_service.refresh_access_token(request.refresh_token)


@router.post("/forgot-password", response_model=dict)
async def forgot_password(request: ResetPasswordRequest):
    """
    Request password reset by sending OTP to email
    
    - **email**: User's email address
    """
    return await auth_service.request_password_reset(request.email)


@router.post("/reset-password", response_model=dict)
async def reset_password(request: ResetPasswordConfirm):
    """
    Reset password using OTP verification
    
    - **email**: User's email address
    - **otp_code**: 6-digit OTP code from email
    - **new_password**: New password (minimum 8 characters)
    """
    return await auth_service.reset_password(
        request.email,
        request.otp_code,
        request.new_password
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_active_user)):
    """
    Get current authenticated user information
    
    Requires valid access token in Authorization header
    """
    return current_user


@router.post("/logout", response_model=dict)
async def logout(current_user: dict = Depends(get_current_active_user)):
    """
    Logout current user (client should delete tokens)
    
    Requires valid access token in Authorization header
    """
    return {"message": "Logout berhasil"}
