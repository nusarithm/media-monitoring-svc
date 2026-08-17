"""Search terms for the social media scraper.

System-wide, not per user: the scraper collects for everyone the way the news
scraper does. Users still narrow results down with their own `user_keywords`.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_active_user
from app.core.database import execute, fetch_all, fetch_one

router = APIRouter(prefix="/sosmed-keywords", tags=["Sosmed Keywords"])

# Platforms the scraper knows how to search. Rejecting unknown values here
# stops a typo from creating a keyword nothing will ever pick up.
PLATFORMS = ("threads", "instagram", "tiktok", "x")


class SosmedKeywordIn(BaseModel):
    keyword: str = Field(..., min_length=2, max_length=200)
    platform: str = Field("threads")
    enabled: bool = True


class SosmedKeyword(SosmedKeywordIn):
    id: int
    last_scraped_at: Optional[str] = None


def _check_platform(platform: str) -> str:
    value = (platform or "").strip().lower()
    if value not in PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"platform harus salah satu dari: {', '.join(PLATFORMS)}",
        )
    return value


@router.get("", response_model=List[SosmedKeyword])
async def list_keywords(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    enabled_only: bool = Query(False, description="Only keywords the scraper will pick up"),
    current_user: dict = Depends(get_current_active_user),
):
    sql = """
        SELECT id, keyword, platform, enabled, last_scraped_at::text AS last_scraped_at
          FROM sosmed_keyword
         WHERE ($1::text IS NULL OR platform = $1)
           AND (NOT $2::boolean OR enabled)
         ORDER BY platform, last_scraped_at NULLS FIRST, keyword
    """
    return await fetch_all(sql, platform, enabled_only)


@router.post("", response_model=SosmedKeyword, status_code=status.HTTP_201_CREATED)
async def create_keyword(body: SosmedKeywordIn, current_user: dict = Depends(get_current_active_user)):
    platform = _check_platform(body.platform)
    row = await fetch_one(
        """
        INSERT INTO sosmed_keyword (keyword, platform, enabled)
        VALUES ($1, $2, $3)
        ON CONFLICT (platform, keyword) DO UPDATE
            SET enabled = EXCLUDED.enabled,
                updated_at = NOW()
        RETURNING id, keyword, platform, enabled, last_scraped_at::text AS last_scraped_at
        """,
        body.keyword.strip(), platform, body.enabled,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Gagal menyimpan keyword")
    return row


@router.put("/{keyword_id}", response_model=SosmedKeyword)
async def update_keyword(
    keyword_id: int,
    body: SosmedKeywordIn,
    current_user: dict = Depends(get_current_active_user),
):
    platform = _check_platform(body.platform)
    row = await fetch_one(
        """
        UPDATE sosmed_keyword
           SET keyword = $2, platform = $3, enabled = $4, updated_at = NOW()
         WHERE id = $1
        RETURNING id, keyword, platform, enabled, last_scraped_at::text AS last_scraped_at
        """,
        keyword_id, body.keyword.strip(), platform, body.enabled,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Keyword tidak ditemukan")
    return row


@router.delete("/{keyword_id}")
async def delete_keyword(keyword_id: int, current_user: dict = Depends(get_current_active_user)):
    result = await execute("DELETE FROM sosmed_keyword WHERE id = $1", keyword_id)
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Keyword tidak ditemukan")
    return {"message": "Keyword dihapus"}
