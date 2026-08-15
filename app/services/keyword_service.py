from app.core.database import fetch_one, execute
from app.models.keyword import KeywordCreate, KeywordUpdate


class KeywordService:
    async def get_user_keywords(self, user_id: int):
        """Get user's keywords"""
        return await fetch_one(
            "SELECT * FROM user_keywords WHERE user_id = $1", user_id
        )

    async def set_keywords(self, user_id: int, keyword_data: KeywordCreate):
        """Set user's keywords (create or update)"""
        # user_keywords has UNIQUE(user_id), so one upsert covers both cases
        result = await fetch_one(
            """
            INSERT INTO user_keywords (user_id, keywords, operator)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE
                SET keywords = EXCLUDED.keywords,
                    operator = EXCLUDED.operator,
                    updated_at = NOW()
            RETURNING *
            """,
            user_id, keyword_data.keywords, keyword_data.operator
        )

        if result is None:
            raise Exception("Failed to set keywords")

        return result

    async def update_keywords(self, user_id: int, keyword_data: KeywordUpdate):
        """Update user's keywords. NULL arguments leave the column untouched."""
        result = await fetch_one(
            """
            UPDATE user_keywords
               SET keywords = COALESCE($2, keywords),
                   operator = COALESCE($3, operator),
                   updated_at = NOW()
             WHERE user_id = $1
            RETURNING *
            """,
            user_id, keyword_data.keywords, keyword_data.operator
        )

        if result is None:
            raise Exception("Keywords not found. Use POST /keywords to create.")

        return result

    async def delete_keywords(self, user_id: int):
        """Delete user's keywords"""
        await execute("DELETE FROM user_keywords WHERE user_id = $1", user_id)
        return {"message": "Keywords deleted successfully"}


keyword_service = KeywordService()
