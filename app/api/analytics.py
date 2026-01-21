from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, List
from datetime import datetime, timedelta
from collections import Counter
import re
from app.models.analytics import (
    AnalyticsFilter, AnalyticsResponse, SummaryCard, TimeSeriesData,
    SentimentDistribution, EmotionData, WordCloudItem
)
from app.core.elasticsearch import es_client
from app.core.config import settings
from app.api.dependencies import get_current_active_user
from app.services.keyword_service import keyword_service


router = APIRouter(prefix="/analytics", tags=["Analytics"])


# Indonesian stopwords
INDONESIAN_STOPWORDS = {
    'yang', 'dan', 'di', 'dari', 'ini', 'itu', 'dengan', 'untuk', 'pada', 'ke', 
    'dalam', 'oleh', 'karena', 'sebagai', 'adalah', 'akan', 'telah', 'dapat', 
    'ada', 'juga', 'atau', 'tidak', 'saat', 'bisa', 'sudah', 'saja', 'tersebut',
    'bahwa', 'lebih', 'antara', 'namun', 'mereka', 'kita', 'kami', 'ia', 'dia',
    'mereka', 'belum', 'hanya', 'masih', 'harus', 'sebuah', 'suatu', 'para',
    'beberapa', 'sering', 'sangat', 'sekali', 'selalu', 'pernah', 'sedang',
    'sendiri', 'paling', 'semua', 'setiap', 'hingga', 'melalui', 'terhadap',
    'tentang', 'tanpa', 'seperti', 'lain', 'banyak', 'jika', 'bila', 'ketika',
    'kalau', 'apakah', 'bagaimana', 'mengapa', 'dimana', 'kapan', 'siapa'
}


def extract_emoji(text: str) -> List[str]:
    """Extract emojis from text"""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.findall(text)


def clean_and_tokenize(text: str) -> List[str]:
    """Clean text and tokenize into words, removing stopwords"""
    # Convert to lowercase
    text = text.lower()
    # Remove URLs
    text = re.sub(r'http\S+|www.\S+', '', text)
    # Remove mentions and hashtags
    text = re.sub(r'@\w+|#\w+', '', text)
    # Remove punctuation and numbers
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\d+', '', text)
    # Split into words
    words = text.split()
    # Filter stopwords and short words
    words = [w for w in words if len(w) > 3 and w not in INDONESIAN_STOPWORDS]
    return words


@router.post("/data", response_model=AnalyticsResponse)
async def get_analytics(
    filters: AnalyticsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Get analytics data with various aggregations
    """
    try:
        print(f"\n=== ANALYTICS DEBUG ===")
        print(f"Date Range: {filters.date_from} to {filters.date_to}")
        print(f"Interval: {filters.interval}")
        
        # Get user's keywords
        user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
        search_keywords = []
        keyword_operator = "OR"
        
        if user_keywords_data:
            search_keywords = user_keywords_data.get("keywords", [])
            keyword_operator = user_keywords_data.get("operator", "OR")
            print(f"User Keywords: {search_keywords} ({keyword_operator})")
        
        # Build base query
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
        
        # Keywords filter
        if search_keywords:
            keyword_queries = []
            for keyword in search_keywords:
                keyword_queries.append({
                    "multi_match": {
                        "query": keyword,
                        "fields": ["title^2", "content"],
                        "type": "best_fields"
                    }
                })
            
            if keyword_operator.upper() == "AND":
                must_clauses.extend(keyword_queries)
            else:
                should_clauses.extend(keyword_queries)
        
        # Build query body
        query_body = {}
        if must_clauses:
            query_body["must"] = must_clauses
        if filter_clauses:
            query_body["filter"] = filter_clauses
        if should_clauses:
            query_body["should"] = should_clauses
            query_body["minimum_should_match"] = 1
        if not must_clauses and not should_clauses:
            query_body["must"] = [{"match_all": {}}]
        
        # Determine date histogram interval
        calendar_interval = "day"
        if filters.interval == "week":
            calendar_interval = "week"
        elif filters.interval == "month":
            calendar_interval = "month"
        
        # Build aggregation query
        agg_query = {
            "size": 0,
            "query": {
                "bool": query_body
            },
            "aggs": {
                # Sentiment counts
                "sentiment_counts": {
                    "terms": {
                        "field": "annotate.sentiment.label.keyword",
                        "size": 10
                    }
                },
                # Time series
                "time_series": {
                    "date_histogram": {
                        "field": "extracted_at",
                        "calendar_interval": calendar_interval,
                        "format": "yyyy-MM-dd",
                        "min_doc_count": 0,
                        "extended_bounds": {
                            "min": filters.date_from,
                            "max": filters.date_to
                        }
                    }
                },
                # Sentiment time series
                "sentiment_time_series": {
                    "date_histogram": {
                        "field": "extracted_at",
                        "calendar_interval": calendar_interval,
                        "format": "yyyy-MM-dd",
                        "min_doc_count": 0
                    },
                    "aggs": {
                        "sentiments": {
                            "terms": {
                                "field": "annotate.sentiment.label.keyword",
                                "size": 10
                            }
                        }
                    }
                },
                # Emotion counts
                "emotion_counts": {
                    "terms": {
                        "field": "annotate.emotion.label.keyword",
                        "size": 20
                    }
                }
            }
        }
        
        print(f"Running aggregation query...")
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body=agg_query
        )
        
        total_docs = result["hits"]["total"]["value"]
        print(f"Total documents: {total_docs}")
        
        # Parse sentiment distribution
        sentiment_counts = {"positif": 0, "negatif": 0, "netral": 0}
        for bucket in result["aggregations"]["sentiment_counts"]["buckets"]:
            key = bucket["key"].lower()
            if key in sentiment_counts:
                sentiment_counts[key] = bucket["doc_count"]
        
        summary = SummaryCard(
            total_news=total_docs,
            total_positive=sentiment_counts["positif"],
            total_negative=sentiment_counts["negatif"],
            total_neutral=sentiment_counts["netral"]
        )
        
        # Parse time series
        time_series = []
        for bucket in result["aggregations"]["time_series"]["buckets"]:
            time_series.append(TimeSeriesData(
                date=bucket["key_as_string"],
                count=bucket["doc_count"]
            ))
        
        # Parse sentiment time series
        sentiment_time_series = {"positive": [], "negative": [], "neutral": []}
        for bucket in result["aggregations"]["sentiment_time_series"]["buckets"]:
            date = bucket["key_as_string"]
            sent_data = {"positif": 0, "negatif": 0, "netral": 0}
            
            for sent_bucket in bucket["sentiments"]["buckets"]:
                key = sent_bucket["key"].lower()
                if key in sent_data:
                    sent_data[key] = sent_bucket["doc_count"]
            
            sentiment_time_series["positive"].append(TimeSeriesData(date=date, count=sent_data["positif"]))
            sentiment_time_series["negative"].append(TimeSeriesData(date=date, count=sent_data["negatif"]))
            sentiment_time_series["neutral"].append(TimeSeriesData(date=date, count=sent_data["netral"]))
        
        # Parse emotions
        emotions = []
        for bucket in result["aggregations"]["emotion_counts"]["buckets"]:
            emotions.append(EmotionData(
                emotion=bucket["key"],
                count=bucket["doc_count"]
            ))
        
        # Now fetch actual documents for word cloud analysis
        # Limit to 1000 docs for performance
        print(f"Fetching documents for wordcloud...")
        docs_query = {
            "query": {
                "bool": query_body
            },
            "size": 1000,
            "_source": ["title", "content"]
        }
        
        docs_result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body=docs_query
        )
        
        # Process documents for wordcloud
        all_text = []
        all_emojis = []
        
        for hit in docs_result["hits"]["hits"]:
            source = hit["_source"]
            text = f"{source.get('title', '')} {source.get('content', '')}"
            all_text.append(text)
            all_emojis.extend(extract_emoji(text))
        
        # Generate emoji wordcloud
        emoji_counter = Counter(all_emojis)
        emoji_wordcloud = [
            WordCloudItem(text=emoji, value=count)
            for emoji, count in emoji_counter.most_common(50)
        ]
        
        # Generate text wordcloud
        all_words = []
        for text in all_text:
            all_words.extend(clean_and_tokenize(text))
        
        word_counter = Counter(all_words)
        text_wordcloud = [
            WordCloudItem(text=word, value=count)
            for word, count in word_counter.most_common(100)
        ]
        
        print(f"Analytics processed successfully")
        print(f"======================\n")
        
        return AnalyticsResponse(
            summary=summary,
            time_series=time_series,
            sentiment_distribution=SentimentDistribution(
                positive=sentiment_counts["positif"],
                negative=sentiment_counts["negatif"],
                neutral=sentiment_counts["netral"]
            ),
            emotions=emotions,
            sentiment_time_series=sentiment_time_series,
            emoji_wordcloud=emoji_wordcloud,
            text_wordcloud=text_wordcloud
        )
        
    except Exception as e:
        import traceback
        print(f"ERROR in analytics: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch analytics: {str(e)}"
        )
