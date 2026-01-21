import random
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from app.core.database import get_supabase, get_supabase_service_role
from app.core.config import settings


class OTPService:
    @staticmethod
    def generate_otp() -> str:
        """Generate a random OTP code"""
        return ''.join(random.choices(string.digits, k=settings.OTP_LENGTH))
    
    @staticmethod
    async def create_otp(user_id: int, otp_code: str) -> Dict[str, Any]:
        """Create OTP record in database (use service role client to bypass RLS)."""
        supabase = get_supabase_service_role()
        expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
        
        result = supabase.table("otp_codes").insert({
            "user_id": user_id,
            "otp_code": otp_code,
            "expires_at": expires_at.isoformat(),
            "is_used": False
        }).execute()
        
        return result.data[0] if result.data else None
    
    @staticmethod
    async def verify_otp(user_id: int, otp_code: str) -> bool:
        """Verify OTP code"""
        # use service role client to bypass RLS when reading/updating OTPs
        supabase = get_supabase_service_role()
        
        # Get the latest unused OTP for this user
        result = supabase.table("otp_codes")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("otp_code", otp_code)\
            .eq("is_used", False)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        
        if not result.data:
            return False
        
        otp_record = result.data[0]
        expires_at = datetime.fromisoformat(otp_record["expires_at"].replace("Z", "+00:00"))
        
        # Check if OTP is expired
        if datetime.utcnow() > expires_at.replace(tzinfo=None):
            return False
        
        # Mark OTP as used
        supabase.table("otp_codes")\
            .update({"is_used": True, "verified_at": datetime.utcnow().isoformat()})\
            .eq("id", otp_record["id"])\
            .execute()
        
        return True
    
    @staticmethod
    async def invalidate_user_otps(user_id: int) -> None:
        """Invalidate all unused OTPs for a user"""
        supabase = get_supabase_service_role()
        supabase.table("otp_codes")\
            .update({"is_used": True})\
            .eq("user_id", user_id)\
            .eq("is_used", False)\
            .execute()


otp_service = OTPService()
