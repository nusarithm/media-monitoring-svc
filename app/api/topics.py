"""Topics: named keyword groups, and comparing them side by side.

The dashboard monitors one flat keyword list per user. A topic is that same
idea named and repeatable, which is what makes "our brand vs competitor"
possible without running the dashboard twice.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_active_user
from app.core.config import settings
from app.core.database import execute, fetch_all, fetch_one
from app.core.elasticsearch import es_client
from app.core.es_query import EMOTION_FIELD, SENTIMENT_FIELD, build_query

router = APIRouter(prefix="/topics", tags=["Topics"])

# Comparing more than this at once makes the chart unreadable long before it
# makes the query slow.
MAX_COMPARE = 6


class TopicIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    keywords: List[str] = Field(..., min_length=1)
    operator: str = Field("OR", pattern="^(AND|OR)$")
    color: Optional[str] = None


class Topic(TopicIn):
    id: int


class CompareFilter(BaseModel):
    date_from: str
    date_to: str
    topic_ids: Optional[List[int]] = Field(None, description="Defaults to all of the user's topics")
    interval: str = Field("day", pattern="^(hour|day|week)$")


class TopicSeries(BaseModel):
    topic_id: int
    name: str
    color: Optional[str]
    total: int
    annotated: int
    sentiment: dict
    emotion: dict
    timeline: List[dict]
    top_sources: List[dict]
    share_of_voice: float


class CompareResponse(BaseModel):
    date_from: str
    date_to: str
    interval: str
    topics: List[TopicSeries]


@router.get("", response_model=List[Topic])
async def list_topics(current_user: dict = Depends(get_current_active_user)):
    rows = await fetch_all(
        "SELECT id, name, keywords, operator, color FROM topics WHERE user_id = $1 ORDER BY name",
        current_user["id"],
    )
    return rows


@router.post("", response_model=Topic, status_code=status.HTTP_201_CREATED)
async def create_topic(body: TopicIn, current_user: dict = Depends(get_current_active_user)):
    row = await fetch_one(
        """
        INSERT INTO topics (user_id, name, keywords, operator, color)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, name) DO UPDATE
            SET keywords = EXCLUDED.keywords,
                operator = EXCLUDED.operator,
                color = EXCLUDED.color,
                updated_at = NOW()
        RETURNING id, name, keywords, operator, color
        """,
        current_user["id"], body.name, body.keywords, body.operator, body.color,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to save topic")
    return row


@router.put("/{topic_id}", response_model=Topic)
async def update_topic(topic_id: int, body: TopicIn, current_user: dict = Depends(get_current_active_user)):
    row = await fetch_one(
        """
        UPDATE topics
           SET name = $3, keywords = $4, operator = $5, color = $6, updated_at = NOW()
         WHERE id = $1 AND user_id = $2
        RETURNING id, name, keywords, operator, color
        """,
        topic_id, current_user["id"], body.name, body.keywords, body.operator, body.color,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return row


@router.delete("/{topic_id}")
async def delete_topic(topic_id: int, current_user: dict = Depends(get_current_active_user)):
    result = await execute("DELETE FROM topics WHERE id = $1 AND user_id = $2", topic_id, current_user["id"])
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"message": "Topic deleted"}


def _series_for(topic: dict, filters: CompareFilter) -> dict:
    query = build_query(
        filters.date_from, filters.date_to,
        keywords=topic["keywords"], operator=topic["operator"],
    )
    result = es_client.search(
        index=settings.ELASTICSEARCH_INDEX,
        body={
            "query": query,
            "size": 0,
            "aggs": {
                "annotated": {"filter": {"exists": {"field": "annotate.sentiment"}}},
                "sentiment": {"terms": {"field": SENTIMENT_FIELD, "size": 5}},
                "emotion": {"terms": {"field": EMOTION_FIELD, "size": 10}},
                "sources": {"terms": {"field": "source_name", "size": 5}},
                "timeline": {
                    "date_histogram": {
                        "field": "scraped_at",
                        "calendar_interval": filters.interval,
                        "min_doc_count": 0,
                    },
                    "aggs": {"negative": {"filter": {"term": {SENTIMENT_FIELD: "negatif"}}}},
                },
            },
        },
    )
    aggs = result["aggregations"]
    return {
        "topic_id": topic["id"],
        "name": topic["name"],
        "color": topic.get("color"),
        "total": result["hits"]["total"]["value"],
        "annotated": aggs["annotated"]["doc_count"],
        "sentiment": {b["key"]: b["doc_count"] for b in aggs["sentiment"]["buckets"]},
        "emotion": {b["key"]: b["doc_count"] for b in aggs["emotion"]["buckets"]},
        "timeline": [
            {
                "date": b["key_as_string"][:10],
                "count": b["doc_count"],
                "negative": b["negative"]["doc_count"],
            }
            for b in aggs["timeline"]["buckets"]
        ],
        "top_sources": [{"name": b["key"], "count": b["doc_count"]} for b in aggs["sources"]["buckets"]],
        "share_of_voice": 0.0,  # filled in once every topic is counted
    }


@router.post("/compare", response_model=CompareResponse)
async def compare_topics(filters: CompareFilter, current_user: dict = Depends(get_current_active_user)):
    """Volume, sentiment and share of voice for several topics over one period."""
    topics = await fetch_all(
        "SELECT id, name, keywords, operator, color FROM topics WHERE user_id = $1 ORDER BY name",
        current_user["id"],
    )
    if filters.topic_ids:
        wanted = set(filters.topic_ids)
        topics = [t for t in topics if t["id"] in wanted]
    topics = topics[:MAX_COMPARE]

    if not topics:
        raise HTTPException(status_code=400, detail="No topics to compare. Create one first.")

    try:
        series = [_series_for(dict(t), filters) for t in topics]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compare failed: {str(e)}")

    # Share of voice is relative to the compared set, not the whole index -
    # that is the number a user actually reads off a comparison.
    grand_total = sum(s["total"] for s in series)
    for s in series:
        s["share_of_voice"] = round(s["total"] / grand_total * 100, 1) if grand_total else 0.0

    return CompareResponse(
        date_from=filters.date_from,
        date_to=filters.date_to,
        interval=filters.interval,
        topics=series,
    )
