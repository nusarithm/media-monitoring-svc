"""Entity drill-down: everything the index knows about one named entity.

The reports and NER pages list entities but dead-end there. This is the other
half: pick "Prabowo" and get the articles, the sentiment trend, and who else
appears alongside.
"""
from collections import Counter
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_active_user
from app.core.config import settings
from app.core.elasticsearch import es_client
from app.core.es_query import EMOTION_FIELD, ENTITY_GROUPS, SENTIMENT_FIELD, build_query

router = APIRouter(prefix="/entities", tags=["Entities"])

CO_OCCURRENCE_SAMPLE = 300


class EntityFilter(BaseModel):
    entity: str = Field(..., min_length=2)
    date_from: str
    date_to: str
    keywords: Optional[List[str]] = None
    operator: str = "OR"
    interval: str = Field("day", pattern="^(hour|day|week)$")
    size: int = Field(20, ge=1, le=100, description="Articles returned")


class EntityArticle(BaseModel):
    id: str
    title: str
    source: str
    url: str
    published_at: Optional[str] = None
    sentiment: Optional[str] = None
    emotion: Optional[str] = None


class EntityDetail(BaseModel):
    entity: str
    total: int
    sentiment: dict
    emotion: dict
    timeline: List[dict]
    top_sources: List[dict]
    co_occurring: List[dict]
    articles: List[EntityArticle]


@router.post("/detail", response_model=EntityDetail)
async def entity_detail(filters: EntityFilter, current_user: dict = Depends(get_current_active_user)):
    query = build_query(
        filters.date_from, filters.date_to,
        keywords=filters.keywords, operator=filters.operator,
        entity=filters.entity,
    )

    try:
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": query,
                "size": filters.size,
                "sort": [{"scraped_at": {"order": "desc"}}],
                "_source": ["title", "source_name", "url", "published_at", "scraped_at",
                            "annotate.sentiment", "annotate.emotion"],
                "aggs": {
                    "sentiment": {"terms": {"field": SENTIMENT_FIELD, "size": 5}},
                    "emotion": {"terms": {"field": EMOTION_FIELD, "size": 10}},
                    "sources": {"terms": {"field": "source_name", "size": 10}},
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

        # Who else shows up in the same articles. Sampled rather than exhaustive:
        # the ranking stabilises long before the last document is read.
        neighbours = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={"query": query, "size": CO_OCCURRENCE_SAMPLE, "_source": ["annotate.entities"]},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Entity lookup failed: {str(e)}")

    target = filters.entity.strip().lower()
    counter: Counter = Counter()
    types: dict = {}
    for doc in neighbours["hits"]["hits"]:
        for ent in (doc["_source"].get("annotate") or {}).get("entities") or []:
            word = (ent.get("word") or "").strip()
            group = ENTITY_GROUPS.get((ent.get("entity_group") or "").upper())
            # Skip the entity itself and anything containing it, otherwise
            # "Prabowo" tops its own co-occurrence list via "Prabowo Subianto".
            if not group or len(word) < 2 or target in word.lower():
                continue
            counter[word] += 1
            types[word] = group

    aggs = result["aggregations"]
    articles = []
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        annotate = src.get("annotate") or {}
        articles.append(EntityArticle(
            id=hit["_id"],
            title=src.get("title", ""),
            source=src.get("source_name", ""),
            url=src.get("url", ""),
            published_at=src.get("published_at") or src.get("scraped_at"),
            sentiment=(annotate.get("sentiment") or {}).get("label"),
            emotion=(annotate.get("emotion") or {}).get("label"),
        ))

    return EntityDetail(
        entity=filters.entity,
        total=result["hits"]["total"]["value"],
        sentiment={b["key"]: b["doc_count"] for b in aggs["sentiment"]["buckets"]},
        emotion={b["key"]: b["doc_count"] for b in aggs["emotion"]["buckets"]},
        timeline=[
            {"date": b["key_as_string"][:10], "count": b["doc_count"], "negative": b["negative"]["doc_count"]}
            for b in aggs["timeline"]["buckets"]
        ],
        top_sources=[{"name": b["key"], "count": b["doc_count"]} for b in aggs["sources"]["buckets"]],
        co_occurring=[{"name": n, "count": c, "type": types[n]} for n, c in counter.most_common(15)],
        articles=articles,
    )
