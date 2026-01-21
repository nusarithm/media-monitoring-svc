from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime


class KeywordCreate(BaseModel):
    """Model for creating keywords"""
    keywords: List[str] = Field(..., min_length=1, max_length=3, description="List of keywords (max 3)")
    operator: str = Field(default="OR", description="Operator for keywords: AND or OR")
    
    @field_validator("keywords")
    def validate_keywords(cls, v):
        if len(v) > 3:
            raise ValueError("Maximum 3 keywords allowed")
        if len(v) == 0:
            raise ValueError("At least 1 keyword required")
        # Remove empty strings and duplicates
        keywords = list(set([k.strip() for k in v if k.strip()]))
        if len(keywords) == 0:
            raise ValueError("At least 1 non-empty keyword required")
        return keywords
    
    @field_validator("operator")
    def validate_operator(cls, v):
        if v.upper() not in ["AND", "OR"]:
            raise ValueError("Operator must be 'AND' or 'OR'")
        return v.upper()


class KeywordUpdate(BaseModel):
    """Model for updating keywords"""
    keywords: Optional[List[str]] = Field(None, max_length=3, description="List of keywords (max 3)")
    operator: Optional[str] = Field(None, description="Operator for keywords: AND or OR")
    
    @field_validator("keywords")
    def validate_keywords(cls, v):
        if v is not None:
            if len(v) > 3:
                raise ValueError("Maximum 3 keywords allowed")
            keywords = list(set([k.strip() for k in v if k.strip()]))
            if len(keywords) == 0:
                raise ValueError("At least 1 non-empty keyword required")
            return keywords
        return v
    
    @field_validator("operator")
    def validate_operator(cls, v):
        if v is not None and v.upper() not in ["AND", "OR"]:
            raise ValueError("Operator must be 'AND' or 'OR'")
        return v.upper() if v else None


class KeywordResponse(BaseModel):
    """Response model for keywords"""
    user_id: int
    keywords: List[str]
    operator: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
