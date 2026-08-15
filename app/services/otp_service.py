import random
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from app.core.database import fetch_one, execute
from app.core.config import settings


class OTPService:
    @staticmethod
    def generate_otp() -> str:
        """Generate a random OTP code"""
        return ''.join(random.choices(string.digits, k=settings.OTP_LENGTH))

    @staticmethod
    async def create_otp(user_id: int, otp_code: str) -> Dict[str, Any]:
        """Create OTP record in database"""
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)

        return await fetch_one(
            """
            INSERT INTO otp_codes (user_id, otp_code, expires_at, is_used)
            VALUES ($1, $2, $3, FALSE)
            RETURNING *
            """,
            user_id, otp_code, expires_at
        )

    @staticmethod
    async def verify_otp(user_id: int, otp_code: str) -> bool:
        """Verify OTP code"""
        # Get the latest unused OTP for this user
        otp_record = await fetch_one(
            """
            SELECT * FROM otp_codes
            WHERE user_id = $1 AND otp_code = $2 AND is_used = FALSE
            ORDER BY created_at DESC
            LIMIT 1
            """,
            user_id, otp_code
        )

        if otp_record is None:
            return False

        # expires_at comes back as a timezone-aware datetime
        if datetime.now(timezone.utc) > otp_record["expires_at"]:
            return False

        # Mark OTP as used
        await execute(
            "UPDATE otp_codes SET is_used = TRUE, verified_at = NOW() WHERE id = $1",
            otp_record["id"]
        )

        return True

    @staticmethod
    async def invalidate_user_otps(user_id: int) -> None:
        """Invalidate all unused OTPs for a user"""
        await execute(
            "UPDATE otp_codes SET is_used = TRUE WHERE user_id = $1 AND is_used = FALSE",
            user_id
        )


otp_service = OTPService()
