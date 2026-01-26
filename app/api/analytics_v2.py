from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, List
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import re
from app.models.analytics import (
    AnalyticsFilter, EntityNetwork, EntityNode, EntityEdge, TimeSeriesData, SentimentDistribution, 
    NamedEntity, NERCategory, NewsSource, SentimentEmotion, 
    CategoryDistribution, EntityRelationship, EmotionBreakdown, 
    SentimentTimeSeries, WordCloudItem, SummaryCard
)
from app.core.elasticsearch import es_client
from app.core.config import settings
from app.api.dependencies import get_current_active_user
from app.services.keyword_service import keyword_service


router = APIRouter(prefix="/analytics/v2", tags=["Analytics V2"])


# Indonesian stopwords
INDONESIAN_STOPWORDS = {
    'yang', 'dan', 'di', 'dari', 'ini', 'itu', 'dengan', 'untuk', 'pada', 'ke', 
    'dalam', 'oleh', 'karena', 'sebagai', 'adalah', 'akan', 'telah', 'dapat', 
    'ada', 'juga', 'atau', 'tidak', 'saat', 'bisa', 'sudah', 'saja', 'tersebut',
    'bahwa', 'lebih', 'antara', 'namun', 'mereka', 'kita', 'kami', 'ia', 'dia',
    'belum', 'hanya', 'masih', 'harus', 'sebuah', 'suatu', 'para', 'beberapa',
    'sering', 'sangat', 'sekali', 'selalu', 'pernah', 'sedang', 'sendiri',
    'paling', 'semua', 'setiap', 'hingga', 'melalui', 'terhadap', 'tentang',
    'tanpa', 'seperti', 'lain', 'banyak', 'jika', 'bila', 'ketika', 'kalau',
    'apakah', 'bagaimana', 'mengapa', 'dimana', 'kapan', 'siapa'
}


def clean_and_tokenize(text: str) -> List[str]:
    """Clean text and tokenize into words, removing stopwords"""
    text = text.lower()
    text = re.sub(r'http\S+|www.\S+', '', text)
    text = re.sub(r'@\w+|#\w+', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\d+', '', text)
    words = text.split()
    words = [w for w in words if len(w) > 3 and w not in INDONESIAN_STOPWORDS]
    return words


def extract_entities(text: str) -> Dict[str, List[str]]:
    """Extract named entities (simplified version)"""
    entities = {
        'organizations': [],
        'people': [],
        'locations': []
    }
    
    org_patterns = [r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+Inc\.?|\s+Corp\.?|\s+Ltd\.?|\s+LLC))\b']
    name_patterns = [r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b']
    loc_keywords = ['Jakarta', 'Surabaya', 'Bandung', 'Indonesia', 'Malaysia', 'Singapore', 
                    'Thailand', 'Philippines', 'Vietnam', 'New York', 'London', 'Tokyo']
    
    for pattern in org_patterns:
        entities['organizations'].extend(re.findall(pattern, text))
    
    for pattern in name_patterns:
        matches = re.findall(pattern, text)
        entities['people'].extend([m for m in matches if not any(org_word in m for org_word in ['Inc', 'Corp', 'Ltd', 'LLC'])])
    
    for loc in loc_keywords:
        if loc in text:
            entities['locations'].append(loc)
    
    return entities


def get_base_query(filters: AnalyticsFilter, search_keywords: List[str], keyword_operator: str):
    """Build base Elasticsearch query"""
    must_clauses = []
    filter_clauses = []
    should_clauses = []
    
    # Date range filter
    filter_clauses.append({
        "range": {
            "extracted_at": {
                "gte": filters.date_from,
                "lte": filters.date_to,
                "format": "yyyy-MM-dd"
            }
        }
    })
    
    # Keyword filter
    if search_keywords:
        if keyword_operator == "AND":
            for keyword in search_keywords:
                must_clauses.append({
                    "multi_match": {
                        "query": keyword,
                        "fields": ["title^3", "description^2", "content"],
                        "type": "best_fields",
                        "operator": "or"
                    }
                })
        else:  # OR
            for keyword in search_keywords:
                should_clauses.append({
                    "multi_match": {
                        "query": keyword,
                        "fields": ["title^3", "description^2", "content"],
                        "type": "best_fields",
                        "operator": "or"
                    }
                })
    
    return {
        "bool": {
            "must": must_clauses,
            "filter": filter_clauses,
            "should": should_clauses,
            "minimum_should_match": 1 if should_clauses and not must_clauses else 0
        }
    }


@router.post("/summary", response_model=SummaryCard)
async def get_summary(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get summary statistics"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "track_total_hits": True,
                "size": 0,
                "aggs": {
                    "sentiment_counts": {
                        "terms": {
                            "field": "annotate.sentiment.label.keyword",
                            "size": 10
                        }
                    }
                }
            }
        )
        
        total_news = result["hits"]["total"]["value"]
        sentiment_buckets = result["aggregations"]["sentiment_counts"]["buckets"]
        
        sentiment_counts = {"positif": 0, "negatif": 0, "netral": 0}
        for bucket in sentiment_buckets:
            if bucket["key"] in sentiment_counts:
                sentiment_counts[bucket["key"]] = bucket["doc_count"]
        
        return SummaryCard(
            total_news=total_news,
            total_positive=sentiment_counts["positif"],
            total_negative=sentiment_counts["negatif"],
            total_neutral=sentiment_counts["netral"]
        )
    except Exception as e:
        import traceback
        print(f"ERROR in summary: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch summary: {str(e)}"
        )


@router.post("/volume-trends", response_model=List[TimeSeriesData])
async def get_volume_trends(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get news volume trends over time"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        interval_map = {"day": "1d", "week": "1w", "month": "1M"}
        es_interval = interval_map.get(filters.interval, "1d")
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 0,
                "aggs": {
                    "volume_over_time": {
                        "date_histogram": {
                            "field": "extracted_at",
                            "calendar_interval": es_interval,
                            "format": "yyyy-MM-dd"
                        }
                    }
                }
            }
        )
        
        return [
            TimeSeriesData(date=bucket["key_as_string"], count=bucket["doc_count"])
            for bucket in result["aggregations"]["volume_over_time"]["buckets"]
        ]
    except Exception as e:
        import traceback
        print(f"ERROR in volume-trends: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch volume trends: {str(e)}"
        )


@router.post("/ner-explorer", response_model=NERCategory)
async def get_ner_explorer(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get Named Entity Recognition data"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 1000,
                "_source": ["title", "description", "content"]
            }
        )
        
        all_entities = {"organizations": [], "people": [], "locations": []}
        
        for doc in result["hits"]["hits"]:
            source = doc["_source"]
            text = f"{source.get('title', '')} {source.get('description', '')} {source.get('content', '')}"
            entities = extract_entities(text)
            for entity_type, entity_list in entities.items():
                all_entities[entity_type].extend(entity_list)
        
        org_counter = Counter(all_entities['organizations'])
        people_counter = Counter(all_entities['people'])
        loc_counter = Counter(all_entities['locations'])
        
        return NERCategory(
            organizations=[NamedEntity(name=name, count=count, type="organization") 
                          for name, count in org_counter.most_common(10)],
            people=[NamedEntity(name=name, count=count, type="person") 
                   for name, count in people_counter.most_common(10)],
            locations=[NamedEntity(name=name, count=count, type="location") 
                      for name, count in loc_counter.most_common(10)]
        )
    except Exception as e:
        import traceback
        print(f"ERROR in ner-explorer: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch NER data: {str(e)}"
        )


@router.post("/top-sources", response_model=List[NewsSource])
async def get_top_sources(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get top news sources"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 0,
                "aggs": {
                    "top_sources": {
                        "terms": {
                            "field": "source.keyword",
                            "size": 10
                        }
                    }
                }
            }
        )
        
        buckets = result.get("aggregations", {}).get("top_sources", {}).get("buckets", [])
        print(f"[analytics_v2] top-sources: found {len(buckets)} buckets (field=source.keyword)")
        # Fallback: if buckets empty, try aggregating on `source` field (some mappings use source as keyword)
        if not buckets:
            alt = es_client.search(
                index=settings.ELASTICSEARCH_INDEX,
                body={
                    "query": base_query,
                    "size": 0,
                    "aggs": {"top_sources_alt": {"terms": {"field": "source", "size": 10}}}
                }
            )
            buckets = alt.get("aggregations", {}).get("top_sources_alt", {}).get("buckets", [])
            print(f"[analytics_v2] top-sources: found {len(buckets)} buckets (field=source)")

        # If still empty, fetch documents and compute counts directly (fallback)
        if not buckets:
            docs = es_client.search(
                index=settings.ELASTICSEARCH_INDEX,
                body={
                    "query": base_query,
                    "size": 1000,
                    "_source": ["source"]
                }
            )
            hits = docs.get("hits", {}).get("hits", [])
            from collections import Counter
            c = Counter()
            for h in hits:
                src = h.get("_source", {}).get("source")
                if not src:
                    continue
                # Handle list, dict, or primitive types
                if isinstance(src, list):
                    for s in src:
                        if not s:
                            continue
                        if isinstance(s, dict):
                            s_name = s.get("name") or s.get("title") or str(s)
                            c[str(s_name)] += 1
                        else:
                            c[str(s)] += 1
                elif isinstance(src, dict):
                    # try common subfields
                    src_name = src.get("name") or src.get("title") or src.get("source") or str(src)
                    c[str(src_name)] += 1
                else:
                    c[str(src)] += 1
            buckets = [(k, v) for k, v in c.most_common(10)]
            print(f"[analytics_v2] top-sources: fallback counted {len(buckets)} sources from docs")
            return [NewsSource(name=name, count=count, articles=count) for name, count in buckets]

        return [
            NewsSource(name=bucket["key"], count=bucket["doc_count"], articles=bucket["doc_count"])
            for bucket in buckets
        ]
    except Exception as e:
        import traceback
        print(f"ERROR in top-sources: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch top sources: {str(e)}"
        )


@router.post("/sentiment-emotion-correlation", response_model=List[SentimentEmotion])
async def get_sentiment_emotion_correlation(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get sentiment vs emotion correlation"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 5000,
                "_source": ["annotate"]
            }
        )
        
        sentiment_emotion_data = defaultdict(lambda: {"positif": 0, "negatif": 0, "netral": 0, "total": 0})
        
        for doc in result["hits"]["hits"]:
            source = doc["_source"]
            if "annotate" in source:
                sentiment = source["annotate"].get("sentiment", {}).get("label", "netral")
                emotion = source["annotate"].get("emotion", {}).get("label", "unknown")
                if emotion and emotion != "unknown":
                    sentiment_emotion_data[emotion][sentiment] += 1
                    sentiment_emotion_data[emotion]["total"] += 1
        
        return [
            SentimentEmotion(
                emotion=emotion,
                negative=data["negatif"],
                neutral=data["netral"],
                positive=data["positif"],
                total=data["total"]
            )
            for emotion, data in sentiment_emotion_data.items()
        ]
    except Exception as e:
        import traceback
        print(f"ERROR in sentiment-emotion-correlation: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sentiment-emotion correlation: {str(e)}"
        )


@router.post("/category-distribution", response_model=List[CategoryDistribution])
async def get_category_distribution(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get news category distribution"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 0,
                "aggs": {
                    "categories": {
                        "terms": {
                            "field": "category.keyword",
                            "size": 10
                        }
                    }
                }
            }
        )
        
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        buckets = result.get("aggregations", {}).get("categories", {}).get("buckets", [])
        print(f"[analytics_v2] category-distribution: found {len(buckets)} buckets (field=category.keyword)")

        # Fallback: if no buckets, try `category` field
        if not buckets:
            alt = es_client.search(
                index=settings.ELASTICSEARCH_INDEX,
                body={
                    "query": base_query,
                    "size": 0,
                    "aggs": {"categories_alt": {"terms": {"field": "category", "size": 10}}}
                }
            )
            buckets = alt.get("aggregations", {}).get("categories_alt", {}).get("buckets", [])
            total = sum(b['doc_count'] for b in buckets) or total
            print(f"[analytics_v2] category-distribution: found {len(buckets)} buckets (field=category)")

        # If still empty, fetch documents and compute counts directly (fallback)
        if not buckets:
            docs = es_client.search(
                index=settings.ELASTICSEARCH_INDEX,
                body={
                    "query": base_query,
                    "size": 1000,
                    "_source": ["category"]
                }
            )
            hits = docs.get("hits", {}).get("hits", [])
            from collections import Counter
            c = Counter()
            for h in hits:
                cat = h.get("_source", {}).get("category")
                if not cat:
                    continue
                # Handle list, dict, or primitive
                if isinstance(cat, list):
                    for item in cat:
                        if item:
                            c[str(item)] += 1
                elif isinstance(cat, dict):
                    name = cat.get("name") or cat.get("label") or cat.get("category") or str(cat)
                    c[str(name)] += 1
                else:
                    c[str(cat)] += 1
            buckets = [(k, v) for k, v in c.most_common(10)]
            total = sum(v for _, v in buckets) or total
            print(f"[analytics_v2] category-distribution: fallback counted {len(buckets)} categories from docs")
            return [CategoryDistribution(category=k, count=v, percentage=round((v/total)*100, 1) if total>0 else 0) for k, v in buckets]

        return [
            CategoryDistribution(
                category=bucket["key"],
                count=bucket["doc_count"],
                percentage=round((bucket["doc_count"] / total * 100), 1) if total > 0 else 0
            )
            for bucket in buckets
        ]
    except Exception as e:
        import traceback
        print(f"ERROR in category-distribution: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch category distribution: {str(e)}"
        )


@router.post("/trending-topics", response_model=List[WordCloudItem])
async def get_trending_topics(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get trending topics"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 1000,
                "_source": ["title", "description", "content"]
            }
        )
        
        all_words = []
        for doc in result["hits"]["hits"]:
            source = doc["_source"]
            text = f"{source.get('title', '')} {source.get('description', '')} {source.get('content', '')}"
            words = clean_and_tokenize(text)
            all_words.extend(words)
        
        word_counter = Counter(all_words)
        
        return [
            WordCloudItem(text=word, value=count)
            for word, count in word_counter.most_common(50)
        ]
    except Exception as e:
        import traceback
        print(f"ERROR in trending-topics: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch trending topics: {str(e)}"
        )


@router.post("/sentiment-breakdown", response_model=SentimentDistribution)
async def get_sentiment_breakdown(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get sentiment breakdown"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 0,
                "aggs": {
                    "sentiment_counts": {
                        "terms": {
                            "field": "annotate.sentiment.label.keyword",
                            "size": 10
                        }
                    }
                }
            }
        )
        
        sentiment_counts = {"positif": 0, "negatif": 0, "netral": 0}
        for bucket in result["aggregations"]["sentiment_counts"]["buckets"]:
            if bucket["key"] in sentiment_counts:
                sentiment_counts[bucket["key"]] = bucket["doc_count"]
        
        return SentimentDistribution(
            positive=sentiment_counts["positif"],
            negative=sentiment_counts["negatif"],
            neutral=sentiment_counts["netral"]
        )
    except Exception as e:
        import traceback
        print(f"ERROR in sentiment-breakdown: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sentiment breakdown: {str(e)}"
        )


@router.post("/emotion-breakdown", response_model=List[EmotionBreakdown])
async def get_emotion_breakdown(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get emotion breakdown"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 0,
                "aggs": {
                    "emotions": {
                        "terms": {
                            "field": "annotate.emotion.label.keyword",
                            "size": 10
                        }
                    }
                }
            }
        )
        
        total = sum(bucket["doc_count"] for bucket in result["aggregations"]["emotions"]["buckets"])
        
        return [
            EmotionBreakdown(
                emotion=bucket["key"],
                count=bucket["doc_count"],
                percentage=round((bucket["doc_count"] / total * 100), 1) if total > 0 else 0
            )
            for bucket in result["aggregations"]["emotions"]["buckets"]
        ]
    except Exception as e:
        import traceback
        print(f"ERROR in emotion-breakdown: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch emotion breakdown: {str(e)}"
        )


@router.post("/sentiment-time-series", response_model=List[SentimentTimeSeries])
async def get_sentiment_time_series(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """Get sentiment analysis over time"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        interval_map = {"day": "1d", "week": "1w", "month": "1M"}
        es_interval = interval_map.get(filters.interval, "1d")
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 0,
                "aggs": {
                    "time_buckets": {
                        "date_histogram": {
                            "field": "extracted_at",
                            "calendar_interval": es_interval,
                            "format": "yyyy-MM-dd"
                        },
                        "aggs": {
                            "sentiments": {
                                "terms": {
                                    "field": "annotate.sentiment.label.keyword",
                                    "size": 10
                                }
                            }
                        }
                    }
                }
            }
        )
        
        time_series = []
        for bucket in result["aggregations"]["time_buckets"]["buckets"]:
            sentiment_counts = {"positif": 0, "negatif": 0, "netral": 0}
            for sent_bucket in bucket["sentiments"]["buckets"]:
                if sent_bucket["key"] in sentiment_counts:
                    sentiment_counts[sent_bucket["key"]] = sent_bucket["doc_count"]
            
            time_series.append(SentimentTimeSeries(
                date=bucket["key_as_string"],
                positive=sentiment_counts["positif"],
                neutral=sentiment_counts["netral"],
                negative=sentiment_counts["negatif"]
            ))
        
        return time_series
    except Exception as e:
        import traceback
        print(f"ERROR in sentiment-time-series: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sentiment time series: {str(e)}"
        )

@router.post("/entity-network", response_model=EntityNetwork)
async def get_entity_network(filters: AnalyticsFilter, current_user: dict = Depends(get_current_active_user)):
    """Return social network analysis: nodes with degree and weighted edges"""
    try:
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
        
        base_query = get_base_query(filters, search_keywords, keyword_operator)
        # Fetch docs for entity extraction
        print("base_query for entity-network:", base_query)
        all_docs_result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body={
                "query": base_query,
                "size": 1000,
                "_source": ["title", "description", "content", "annotate"]
            }
        )
        print(f"[analytics_v2] entity-network: fetched {all_docs_result.get('hits', {}).get('total', {}).get('value', len(all_docs_result.get('hits', {}).get('hits', [])))} docs (requested 1000)")
        all_docs = all_docs_result.get("hits", {}).get("hits", [])

        # Build co-occurrence counts and record entity types
        pair_counts = Counter()
        node_weights = Counter()
        entity_types = defaultdict(set)

        for doc in all_docs:
            src = doc.get("_source", {})

            # Prefer using structured `annotate.entities` when available
            doc_entities = []
            annotate = src.get('annotate') or {}
            entities_list = []
            if isinstance(annotate, dict):
                entities_list = annotate.get('entities') if isinstance(annotate.get('entities'), list) else []

            
            for ent in entities_list:
                word = (ent.get('word') or ent.get('text') or '').strip()
                if not word or len(word) <= 1:
                    continue
                group = (ent.get('entity_group') or ent.get('group') or '').upper()
                # Only consider PER (person), LOC (location), ORG (organization)
                if group == 'PER':
                    entity_types[word].add('person')
                    doc_entities.append(word)
                elif group == 'LOC' or group == 'GPE':
                    entity_types[word].add('location')
                    doc_entities.append(word)
                elif group == 'ORG' or group == 'NOR' or group == 'ORGANIZATION':
                    entity_types[word].add('organization')
                    doc_entities.append(word)
                else:
                    # skip other groups (e.g., cardinal numbers, dates)
                    continue
            
            # unique entities per doc to avoid double counting in same doc
            unique_entities = list(dict.fromkeys(doc_entities))
            for i, e1 in enumerate(unique_entities):
                node_weights[e1] += 1
                for e2 in unique_entities[i+1:]:
                    # normalize pair ordering
                    a, b = (e1, e2) if e1 <= e2 else (e2, e1)
                    pair_counts[(a, b)] += 1

            # Debug: sample entities for inspection
            if doc_entities:
                print(f"[analytics_v2] entity-network: doc {doc.get('_id')} entities: {doc_entities[:8]}")

        # Build nodes and edges
        nodes = []
        edges = []

        # degrees: sum of incident edge weights
        degree_map = Counter()
        for (a, b), w in pair_counts.items():
            degree_map[a] += w
            degree_map[b] += w
            edges.append(EntityEdge(source=a, target=b, value=w))

        for name, weight in node_weights.items():
            types = entity_types.get(name, set())
            if not types:
                grp = None
            elif len(types) == 1:
                grp = next(iter(types))
            else:
                grp = 'mixed'
            nodes.append(EntityNode(id=name, label=name, degree=degree_map.get(name, 0), weight=weight, group=grp))

        # sort nodes by degree desc
        nodes_sorted = sorted(nodes, key=lambda n: n.degree, reverse=True)
        # keep top 50 nodes and filter edges accordingly
        top_node_ids = set([n.id for n in nodes_sorted[:50]])
        filtered_nodes = [n for n in nodes_sorted if n.id in top_node_ids]
        filtered_edges = [e for e in edges if e.source in top_node_ids and e.target in top_node_ids]

        return EntityNetwork(nodes=filtered_nodes, edges=filtered_edges)
    except Exception as e:
        import traceback
        print(f"ERROR in entity-network: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
