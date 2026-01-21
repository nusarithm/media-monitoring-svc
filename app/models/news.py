from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class NewsFilter(BaseModel):
    """Filter parameters for news search"""
    date_from: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    sources: Optional[List[str]] = Field(None, description="List of source names")
    sentiment: Optional[str] = Field(None, description="Sentiment filter: positif, negatif, netral")
    keywords: Optional[List[str]] = Field(None, description="Keywords to search (uses user's saved keywords if not provided)")
    keyword_operator: Optional[str] = Field(None, description="Keyword operator: AND or OR (uses user's setting if not provided)")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(10, ge=1, le=100, description="Items per page")


class NewsArticle(BaseModel):
    """News article model"""
    id: str
    title: str
    content: Optional[str] = None
    source: str
    url: str
    author: Optional[str] = None
    publish_date: Optional[str] = None
    publish_date_timestamp: Optional[int] = None
    extracted_at: Optional[str] = None
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    emotion: Optional[str] = None
    emotion_score: Optional[float] = None
    tags: Optional[List[str]] = None
    headline_image: Optional[str] = None


class NewsResponse(BaseModel):
    """Response model for news list"""
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[NewsArticle]
    keywords: Optional[List[str]] = Field(None, description="Keywords used for filtering")
    keyword_operator: Optional[str] = Field(None, description="Operator used: AND or OR")


class SourceResponse(BaseModel):
    """Response model for sources"""
    sources: List[str]
    total: int
