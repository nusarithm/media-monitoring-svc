"""Shared Elasticsearch query construction.

Every feature that reads the news index needs the same shape: a date range,
a keyword set combined with AND/OR, and optional source/sentiment filters.
Keeping it here means the annotation field names live in one place.
"""
from typing import List, Optional

SENTIMENT_FIELD = "annotate.sentiment.label.keyword"
EMOTION_FIELD = "annotate.emotion.label.keyword"

# The NER model tags locations GPE rather than LOC. Groups outside this map
# (dates, numbers, products) are noise in an entity report.
ENTITY_GROUPS = {
    "PER": "people",
    "ORG": "organizations", "NOR": "organizations", "ORGANIZATION": "organizations",
    "LOC": "locations", "GPE": "locations",
}


def keyword_clauses(keywords: List[str]):
    return [
        {"multi_match": {"query": k, "fields": ["title^3", "body"], "type": "best_fields"}}
        for k in (keywords or [])
    ]


def build_query(
    date_from: str,
    date_to: str,
    keywords: Optional[List[str]] = None,
    operator: str = "OR",
    sources: Optional[List[str]] = None,
    sentiment: Optional[str] = None,
    entity: Optional[str] = None,
    date_field: str = "scraped_at",
) -> dict:
    """Bool query for the news index.

    `date_to` is inclusive: the caller passes a plain date, and a range that
    stopped at midnight would silently drop everything published that day.
    """
    must: list = [{
        "range": {date_field: {"gte": date_from, "lte": f"{date_to}T23:59:59"}}
    }]
    filters: list = []

    matches = keyword_clauses(keywords)
    if matches:
        if (operator or "OR").upper() == "AND":
            must.extend(matches)
        else:
            filters.append({"bool": {"should": matches, "minimum_should_match": 1}})

    if sources:
        filters.append({"terms": {"source_name": sources}})
    if sentiment:
        filters.append({"term": {SENTIMENT_FIELD: sentiment}})
    if entity:
        # Matched on the analysed text field, so "prabowo" finds "Prabowo
        # Subianto". The keyword subfield would demand the exact full string.
        filters.append({"match_phrase": {"annotate.entities.word": entity}})

    return {"bool": {"must": must, "filter": filters}}


def count_entities(hits, counters):
    """Tally `annotate.entities` from ES hits into {bucket: Counter}.

    Pairing happens here rather than in an aggregation because
    `annotate.entities` is a plain object array: Elasticsearch flattens it, so
    a terms agg on `word` filtered by `entity_group` mixes a document's words
    across its own entities.
    """
    for doc in hits:
        for ent in (doc["_source"].get("annotate") or {}).get("entities") or []:
            bucket = ENTITY_GROUPS.get((ent.get("entity_group") or "").upper())
            word = (ent.get("word") or "").strip()
            if bucket and len(word) > 1:
                counters[bucket][word] += 1
    return counters
