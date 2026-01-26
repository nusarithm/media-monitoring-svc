from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional, List
from datetime import datetime, timedelta
from app.models.news import NewsFilter, NewsArticle, NewsResponse, SourceResponse
from app.core.elasticsearch import es_client
from app.core.config import settings
from app.api.dependencies import get_current_active_user


router = APIRouter(prefix="/news", tags=["News"])


@router.get("/sources", response_model=SourceResponse)
async def get_sources(current_user: dict = Depends(get_current_active_user)):
    """
    Get list of all available news sources from Elasticsearch
    """
    try:
        # Aggregation query to get unique sources
        query = {
            "size": 0,
            "aggs": {
                "unique_sources": {
                    "terms": {
                        "field": "source",
                        "size": 1000,
                        "order": {
                            "_key": "asc"
                        }
                    }
                }
            }
        }
        
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body=query
        )
        
        # Extract sources from aggregation
        sources = []
        if "aggregations" in result and "unique_sources" in result["aggregations"]:
            buckets = result["aggregations"]["unique_sources"]["buckets"]
            sources = [bucket["key"] for bucket in buckets]
        
        return SourceResponse(
            sources=sources,
            total=len(sources)
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch sources: {str(e)}"
        )


@router.post("/search", response_model=NewsResponse)
async def search_news(
    filters: NewsFilter,
    current_user: dict = Depends(get_current_active_user)
):
    """
    Search news articles with filters
    
    - **date_from**: Start date (YYYY-MM-DD), default: 7 days ago
    - **date_to**: End date (YYYY-MM-DD), default: today
    - **sources**: List of source names to filter
    - **sentiment**: Filter by sentiment (positif, negatif, netral)
    - **keywords**: List of keywords to search (will use user's saved keywords if not provided)
    - **keyword_operator**: Operator for keywords (AND/OR, default from user settings)
    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 10, max: 100)
    """
    try:
        print(f"\n=== NEWS SEARCH DEBUG ===")
        print(f"User ID: {current_user.get('id')}")
        print(f"Filter Keywords: {filters.keywords}")
        print(f"Filter Operator: {filters.keyword_operator}")
        
        # Get user's keywords if not provided in filter
        from app.services.keyword_service import keyword_service
        
        user_keywords_data = None
        try:
            user_keywords_data = await keyword_service.get_user_keywords(current_user["id"])
            print(f"User Keywords Data: {user_keywords_data}")
        except Exception as ke:
            print(f"Error getting keywords: {str(ke)}")
        
        # Use filter keywords if provided, otherwise use user's saved keywords
        search_keywords = filters.keywords if filters.keywords else None
        keyword_operator = filters.keyword_operator if filters.keyword_operator else "OR"
        
        if user_keywords_data:
            if not search_keywords:
                search_keywords = user_keywords_data.get("keywords", [])
            if not filters.keyword_operator:
                keyword_operator = user_keywords_data.get("operator", "OR")
        
        print(f"Final Keywords: {search_keywords}")
        print(f"Final Operator: {keyword_operator}")
        print(f"=========================\n")
        
        # Build query
        must_clauses = []
        filter_clauses = []
        should_clauses = []
        
        # Date range filter
        date_from = filters.date_from
        date_to = filters.date_to
        
        if not date_from:
            # Default: 7 days ago
            date_from = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        # change date string to timestamp seconds
        date_from_stamp = int(datetime.strptime(date_from, "%Y-%m-%d").timestamp())
        date_to_stamp = int(datetime.strptime(date_to, "%Y-%m-%d").timestamp()) if date_to else int(datetime.now().timestamp())
        
        if not date_to:
            # Default: today
            date_to = datetime.now().strftime("%Y-%m-%d")
        
        # Use publish_date_timestamp for date filtering (it's a date type)
        filter_clauses.append({
            "range": {
                "publish_date_timestamp": {
                    "gte": date_from_stamp,
                    "lte": date_to_stamp,
                    "format": "yyyy-MM-dd"
                }
            }
        })
        
        # Keywords filter - search in title and content
        if search_keywords and len(search_keywords) > 0:
            keyword_queries = []
            for keyword in search_keywords:
                keyword_queries.append({
                    "multi_match": {
                        "query": keyword,
                        "fields": ["title^2", "content"],
                        "type": "best_fields",
                        "operator": "or"
                    }
                })
            
            if keyword_operator.upper() == "AND":
                # All keywords must match
                must_clauses.extend(keyword_queries)
            else:
                # At least one keyword must match (OR)
                should_clauses.extend(keyword_queries)
        
        # Source filter
        if filters.sources and len(filters.sources) > 0:
            filter_clauses.append({
                "terms": {
                    "source": filters.sources
                }
            })
        
        # Sentiment filter
        if filters.sentiment:
            filter_clauses.append({
                "term": {
                    "annotate.sentiment.label.keyword": filters.sentiment
                }
            })
        
        # Calculate pagination
        from_index = (filters.page - 1) * filters.page_size
        
        # Build final query
        query_body = {}
        
        if must_clauses:
            query_body["must"] = must_clauses
        
        if filter_clauses:
            query_body["filter"] = filter_clauses
        
        if should_clauses:
            query_body["should"] = should_clauses
            query_body["minimum_should_match"] = 1
        
        # If no specific conditions, match all
        if not must_clauses and not should_clauses:
            query_body["must"] = [{"match_all": {}}]
        
        query = {
            "query": {
                "bool": query_body
            },
            "sort": [
                {"publish_date_timestamp": {"order": "desc"}}
            ],
            "from": from_index,
            "size": filters.page_size
        }
        
        print(f"Elasticsearch Query: {query}")
        
        # Execute search
        result = es_client.search(
            index=settings.ELASTICSEARCH_INDEX,
            body=query
        )
        
        print(f"ES Response - Total: {result['hits']['total']['value']}")
        
        # Parse results
        total = result["hits"]["total"]["value"]
        items = []
        
        for hit in result["hits"]["hits"]:
            source_data = hit["_source"]
            
            # Extract sentiment info
            sentiment = None
            sentiment_score = None
            if "annotate" in source_data and "sentiment" in source_data["annotate"]:
                sentiment = source_data["annotate"]["sentiment"].get("label")
                sentiment_score = source_data["annotate"]["sentiment"].get("score")
            
            # Extract emotion info
            emotion = None
            emotion_score = None
            if "annotate" in source_data and "emotion" in source_data["annotate"]:
                emotion = source_data["annotate"]["emotion"].get("label")
                emotion_score = source_data["annotate"]["emotion"].get("score")
            
            # Handle tags - convert string to list if needed
            tags = source_data.get("tags")
            if tags is not None and isinstance(tags, str):
                tags = [tags]
            
            article = NewsArticle(
                id=hit["_id"],
                title=source_data.get("title", ""),
                content=source_data.get("content"),
                source=source_data.get("source", ""),
                url=source_data.get("url", ""),
                author=source_data.get("author"),
                publish_date=source_data.get("publish_date"),
                publish_date_timestamp=source_data.get("publish_date_timestamp"),
                extracted_at=source_data.get("extracted_at"),
                sentiment=sentiment,
                sentiment_score=sentiment_score,
                emotion=emotion,
                emotion_score=emotion_score,
                tags=tags,
                headline_image=source_data.get("headline_image")
            )
            items.append(article)
        
        # Calculate total pages
        total_pages = (total + filters.page_size - 1) // filters.page_size
        
        return NewsResponse(
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
            items=items,
            keywords=search_keywords if search_keywords else None,
            keyword_operator=keyword_operator if search_keywords else None
        )
        
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(f"ERROR in search_news: {str(e)}")
        print(traceback.format_exc())
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search news: {str(e)}"
        )
