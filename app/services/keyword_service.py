from typing import List, Optional
from datetime import datetime
from supabase import Client
from app.core.database import SupabaseServiceClient
from app.models.keyword import KeywordCreate, KeywordUpdate


class KeywordService:
    def __init__(self):
        self.supabase: Client = SupabaseServiceClient.get_client()
    
    async def get_user_keywords(self, user_id: int):
        """Get user's keywords"""
        result = self.supabase.table("user_keywords")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    
    async def set_keywords(self, user_id: int, keyword_data: KeywordCreate):
        """Set user's keywords (create or update)"""
        # Check if user already has keywords
        existing = await self.get_user_keywords(user_id)
        
        now = datetime.utcnow().isoformat()
        
        data = {
            "user_id": user_id,
            "keywords": keyword_data.keywords,
            "operator": keyword_data.operator,
            "updated_at": now
        }
        
        if existing:
            # Update existing
            result = self.supabase.table("user_keywords")\
                .update(data)\
                .eq("user_id", user_id)\
                .execute()
        else:
            # Create new
            data["created_at"] = now
            result = self.supabase.table("user_keywords")\
                .insert(data)\
                .execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        
        raise Exception("Failed to set keywords")
    
    async def update_keywords(self, user_id: int, keyword_data: KeywordUpdate):
        """Update user's keywords"""
        existing = await self.get_user_keywords(user_id)
        
        if not existing:
            raise Exception("Keywords not found. Use POST /keywords to create.")
        
        update_data = {}
        
        if keyword_data.keywords is not None:
            update_data["keywords"] = keyword_data.keywords
        
        if keyword_data.operator is not None:
            update_data["operator"] = keyword_data.operator
        
        if not update_data:
            return existing
        
        update_data["updated_at"] = datetime.utcnow().isoformat()
        
        result = self.supabase.table("user_keywords")\
            .update(update_data)\
            .eq("user_id", user_id)\
            .execute()
        
        if result.data and len(result.data) > 0:
            return result.data[0]
        
        raise Exception("Failed to update keywords")
    
    async def delete_keywords(self, user_id: int):
        """Delete user's keywords"""
        result = self.supabase.table("user_keywords")\
            .delete()\
            .eq("user_id", user_id)\
            .execute()
        
        return {"message": "Keywords deleted successfully"}


keyword_service = KeywordService()
