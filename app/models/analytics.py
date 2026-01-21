from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


class AnalyticsFilter(BaseModel):
    """Filter parameters for analytics"""
    date_from: str = Field(..., description="Start date (YYYY-MM-DD)")
    date_to: str = Field(..., description="End date (YYYY-MM-DD)")
    interval: Optional[str] = Field("day", description="Interval: day, week, month")


class SummaryCard(BaseModel):
    """Summary card data"""
    total_news: int
    total_positive: int
    total_negative: int
    total_neutral: int


class TimeSeriesData(BaseModel):
    """Time series data point"""
    date: str
    count: int


class SentimentDistribution(BaseModel):
    """Sentiment distribution for donut chart"""
    positive: int
    negative: int
    neutral: int


class EmotionData(BaseModel):
    """Emotion data point"""
    emotion: str
    count: int


class WordCloudItem(BaseModel):
    """Word cloud item"""
    text: str
    value: int


class AnalyticsResponse(BaseModel):
    """Analytics response"""
    summary: SummaryCard
    time_series: List[TimeSeriesData]
    sentiment_distribution: SentimentDistribution
    emotions: List[EmotionData]
    sentiment_time_series: Dict[str, List[TimeSeriesData]]  # {positive: [], negative: [], neutral: []}
    emoji_wordcloud: List[WordCloudItem]
    text_wordcloud: List[WordCloudItem]
