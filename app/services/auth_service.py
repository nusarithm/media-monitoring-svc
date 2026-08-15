from typing import Optional, Dict, Any
from app.core.database import fetch_one, execute, get_pool
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
        """Get user by email"""
        return await fetch_one("SELECT * FROM users WHERE email = $1", email)

    @staticmethod
    async def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID"""
        return await fetch_one("SELECT * FROM users WHERE id = $1", user_id)

    @staticmethod
    async def create_user(user_data: UserCreate) -> Dict[str, Any]:
        """Create a new user. Creates a workspace first and links the user to it."""
        existing_user = await AuthService.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email sudah terdaftar"
            )

        workspace_name = f"{user_data.name or user_data.email.split('@')[0]}'s Workspace"
        hashed_password = get_password_hash(user_data.password)

        # Workspace and user are created together - the transaction rolls back
        # both if either insert fails.
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                workspace_id = await conn.fetchval(
                    "INSERT INTO workspace (workspace_name) VALUES ($1) RETURNING id",
                    workspace_name
                )
                row = await conn.fetchrow(
                    """
                    INSERT INTO users (email, name, phone, password, is_active, workspace_id)
                    VALUES ($1, $2, $3, $4, FALSE, $5)
                    RETURNING *
                    """,
                    user_data.email, user_data.name, user_data.phone,
                    hashed_password, workspace_id
                )

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gagal membuat user"
            )

        return dict(row)
    
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
        
        # Activate user
        await execute("UPDATE users SET is_active = TRUE WHERE id = $1", user["id"])

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
        
        # Update password - fail loudly if no row was written
        hashed_password = get_password_hash(new_password)
        updated = await fetch_one(
            "UPDATE users SET password = $1 WHERE id = $2 RETURNING id",
            hashed_password, user["id"]
        )
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Gagal memperbarui password"
            )

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
