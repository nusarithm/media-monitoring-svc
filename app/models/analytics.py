from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
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


# NEW MODELS FOR COMPREHENSIVE ANALYTICS

class NamedEntity(BaseModel):
    """Named Entity Recognition item"""
    name: str
    count: int
    type: str  # organization, person, location


class NERCategory(BaseModel):
    """NER by category"""
    organizations: List[NamedEntity]
    people: List[NamedEntity]
    locations: List[NamedEntity]


class NewsSource(BaseModel):
    """News source with count"""
    name: str
    count: int
    articles: int


class SentimentEmotion(BaseModel):
    """Sentiment vs Emotion correlation"""
    emotion: str
    negative: int
    neutral: int
    positive: int
    total: int


class CategoryDistribution(BaseModel):
    """News category distribution"""
    category: str
    count: int
    percentage: float


class EntityRelationship(BaseModel):
    """Entity co-occurrence relationship"""
    source: str
    target: str
    value: int  # co-occurrence count


class EntityNode(BaseModel):
    """Entity node for network graph"""
    id: str
    label: str
    degree: int
    weight: int
    group: Optional[str] = None


class EntityEdge(BaseModel):
    """Edge between entities"""
    source: str
    target: str
    value: int


class EntityNetwork(BaseModel):
    """Network representation for social graph"""
    nodes: List[EntityNode]
    edges: List[EntityEdge]


class EmotionBreakdown(BaseModel):
    """Emotion distribution breakdown"""
    emotion: str
    count: int
    percentage: float


class SentimentTimeSeries(BaseModel):
    """Sentiment over time data point"""
    date: str
    positive: int
    neutral: int
    negative: int


class AnalyticsResponse(BaseModel):
    """Analytics response"""
    summary: SummaryCard
    time_series: List[TimeSeriesData]
    sentiment_distribution: SentimentDistribution
    emotions: List[EmotionData]
    sentiment_time_series: Dict[str, List[TimeSeriesData]]  # {positive: [], negative: [], neutral: []}
    emoji_wordcloud: List[WordCloudItem]
    text_wordcloud: List[WordCloudItem]


class ComprehensiveAnalyticsResponse(BaseModel):
    """Comprehensive analytics response with all dashboard data"""
    # Volume trends
    volume_trends: List[TimeSeriesData]
    
    # Named Entity Recognition
    ner_explorer: NERCategory
    top_entities: List[NamedEntity]
    entity_relationships: List[EntityRelationship]
    
    # News sources
    top_sources: List[NewsSource]
    
    # Sentiment & Emotion
    sentiment_emotion_correlation: List[SentimentEmotion]
    sentiment_breakdown: SentimentDistribution
    emotion_breakdown: List[EmotionBreakdown]
    sentiment_time_series: List[SentimentTimeSeries]
    
    # Categories
    category_distribution: List[CategoryDistribution]
    
    # Trending topics
    trending_topics: List[WordCloudItem]
    
    # Summary
    summary: SummaryCard
