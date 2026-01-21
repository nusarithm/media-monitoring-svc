from typing import Optional, Dict, Any
from datetime import datetime
from app.core.database import get_supabase
from app.core.security import verify_password, get_password_hash
from app.core.jwt import create_access_token, create_refresh_token, decode_token
from app.models.user import UserCreate, UserInDB, UserLogin
from app.models.token import Token
from app.services.otp_service import otp_service
from app.services.email_service import email_service
from fastapi import HTTPException, status


class AuthService:
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
        """Get user by email (use service role client to ensure server-side access)."""
        from app.core.database import get_supabase_service_role
        supabase = get_supabase_service_role()
        result = supabase.table("users").select("*").eq("email", email).execute()
        return result.data[0] if result.data else None
    
    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID (use service role client for server-side access)."""
        from app.core.database import get_supabase_service_role
        supabase = get_supabase_service_role()
        result = supabase.table("users").select("*").eq("id", user_id).execute()
        return result.data[0] if result.data else None
    
    @staticmethod
    async def create_user(user_data: UserCreate) -> Dict[str, Any]:
        """Create a new user. Creates a workspace first and links the user to it."""
        # Use Supabase service role client for admin operations (bypass RLS)
        from app.core.database import get_supabase_service_role
        supabase = get_supabase_service_role()
        
        # Check if user already exists (uses public users table via anon client)
        existing_user = await AuthService.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email sudah terdaftar"
            )
        
        # Create workspace first using service role client
        workspace_name = f"{user_data.name or user_data.email.split('@')[0]}'s Workspace"
        try:
            workspace_result = supabase.table("workspace").insert({
                "workspace_name": workspace_name
            }).execute()
        except Exception as e:
            err = str(e)
            # Provide actionable error message for common causes
            if "Invalid API key" in err or "service_role" in err:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Supabase service role key tidak valid atau belum diatur. Pastikan SUPABASE_SERVICE_ROLE_KEY di `.env` benar."
                )
            if "row-level security" in err.lower():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Gagal membuat workspace karena kebijakan RLS. Pastikan menggunakan service role key atau kebijakan RLS diatur untuk insert."
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gagal membuat workspace: {err}"
            )
        
        if not workspace_result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gagal membuat workspace"
            )
        workspace_id = workspace_result.data[0]["id"]
        
        # Hash password
        hashed_password = get_password_hash(user_data.password)
        
        # Create user with workspace_id (use service role to avoid RLS issues)
        user_dict = {
            "email": user_data.email,
            "name": user_data.name,
            "phone": user_data.phone,
            "password": hashed_password,
            "is_active": False,  # User needs to verify email first
            "workspace_id": workspace_id
        }
        
        result = supabase.table("users").insert(user_dict).execute()
        
        if not result.data:
            # Rollback workspace if user creation failed
            try:
                supabase.table("workspace").delete().eq("id", workspace_id).execute()
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gagal membuat user"
            )
        
        return result.data[0]
    
    @staticmethod
    async def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user with email and password"""
        user = await AuthService.get_user_by_email(email)
        if not user:
            return None
        
        if not verify_password(password, user["password"]):
            return None
        
        return user
    
    @staticmethod
    async def login(credentials: UserLogin) -> Token:
        """Login user and return tokens"""
        user = await AuthService.authenticate_user(credentials.email, credentials.password)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Email atau password salah",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Akun belum diverifikasi. Silakan cek email Anda.",
            )
        
        # Create tokens
        access_token = create_access_token(
            data={"sub": str(user["id"]), "email": user["email"]}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user["id"]), "email": user["email"]}
        )
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
    
    @staticmethod
    async def register(user_data: UserCreate) -> Dict[str, str]:
        """Register new user and send OTP"""
        # Create user
        user = await AuthService.create_user(user_data)
        
        # Generate and send OTP
        otp_code = otp_service.generate_otp()
        await otp_service.create_otp(user["id"], otp_code)
        
        # Send OTP email
        email_sent = await email_service.send_otp_email(
            to_email=user["email"],
            otp_code=otp_code,
            name=user.get("name")
        )
        
        if not email_sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gagal mengirim email OTP"
            )
        
        return {
            "message": "Registrasi berhasil. Silakan cek email untuk kode OTP.",
            "email": user["email"]
        }
    
    @staticmethod
    async def verify_email(email: str, otp_code: str) -> Token:
        """Verify email with OTP and activate user"""
        user = await AuthService.get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User tidak ditemukan"
            )
        
        # Verify OTP
        is_valid = await otp_service.verify_otp(user["id"], otp_code)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kode OTP tidak valid atau sudah kedaluwarsa"
            )
        
        # Activate user using service role client (bypass RLS)
        from app.core.database import get_supabase_service_role
        supabase = get_supabase_service_role()
        supabase.table("users").update({"is_active": True}).eq("id", user["id"]).execute()
        
        # Create tokens
        access_token = create_access_token(
            data={"sub": str(user["id"]), "email": user["email"]}
        )
        refresh_token = create_refresh_token(
            data={"sub": str(user["id"]), "email": user["email"]}
        )
        
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer"
        )
    
    @staticmethod
    async def resend_otp(email: str) -> Dict[str, str]:
        """Resend OTP to user email"""
        user = await AuthService.get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User tidak ditemukan"
            )
        
        # Invalidate old OTPs
        await otp_service.invalidate_user_otps(user["id"])
        
        # Generate new OTP
        otp_code = otp_service.generate_otp()
        await otp_service.create_otp(user["id"], otp_code)
        
        # Send OTP email
        email_sent = await email_service.send_otp_email(
            to_email=user["email"],
            otp_code=otp_code,
            name=user.get("name")
        )
        
        if not email_sent:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gagal mengirim email OTP"
            )
        
        return {
            "message": "Kode OTP baru telah dikirim ke email Anda",
            "email": user["email"]
        }
    
    @staticmethod
    async def request_password_reset(email: str) -> Dict[str, str]:
        """Request password reset by sending OTP"""
        user = await AuthService.get_user_by_email(email)
        if not user:
            # Return success even if user not found (security best practice)
            return {
                "message": "Jika email terdaftar, kode OTP akan dikirim",
                "email": email
            }
        
        # Invalidate old OTPs
        await otp_service.invalidate_user_otps(user["id"])
        
        # Generate new OTP
        otp_code = otp_service.generate_otp()
        await otp_service.create_otp(user["id"], otp_code)
        
        # Send password reset email
        await email_service.send_password_reset_email(
            to_email=user["email"],
            otp_code=otp_code,
            name=user.get("name")
        )
        
        return {
            "message": "Jika email terdaftar, kode OTP akan dikirim",
            "email": email
        }
    
    @staticmethod
    async def reset_password(email: str, otp_code: str, new_password: str) -> Dict[str, str]:
        """Reset password with OTP verification"""
        user = await AuthService.get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User tidak ditemukan"
            )
        
        # Verify OTP
        is_valid = await otp_service.verify_otp(user["id"], otp_code)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kode OTP tidak valid atau sudah kedaluwarsa"
            )
        
        # Update password
        hashed_password = get_password_hash(new_password)
        supabase = get_supabase()
        supabase.table("users").update({"password": hashed_password}).eq("id", user["id"]).execute()
        
        return {
            "message": "Password berhasil direset"
        }
    
    @staticmethod
    async def refresh_access_token(refresh_token: str) -> Token:
        """Refresh access token using refresh token"""
        payload = decode_token(refresh_token)
        
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user_id = payload.get("sub")
        email = payload.get("email")
        
        # Create new tokens
        access_token = create_access_token(
            data={"sub": user_id, "email": email}
        )
        new_refresh_token = create_refresh_token(
            data={"sub": user_id, "email": email}
        )
        
        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="bearer"
        )


auth_service = AuthService()
