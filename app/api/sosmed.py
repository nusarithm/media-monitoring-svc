"""Social media posts: the feed, and the numbers behind it.

Reads the indices the social scraper writes (`threads_posts`) with the same
`annotate` block the news pipeline produces, so sentiment and entities work
exactly as they do for articles. Engagement counts are the part news does not
have: likes, comments, reposts, quotes.
"""
from typing import List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_active_user
from app.core.elasticsearch import es_client
from app.core.es_query import EMOTION_FIELD, SENTIMENT_FIELD
from app.core.image_proxy import fetch_image

router = APIRouter(prefix="/sosmed", tags=["Social Media"])

POSTS_INDEX = "threads_posts"
PROFILES_INDEX = "threads_profiles"

# The scraper writes one index per platform; only Threads exists so far.
PLATFORM_INDEX = {"threads": POSTS_INDEX}


class SosmedFilter(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    platform: str = "threads"
    keywords: Optional[List[str]] = Field(None, description="Scraper keywords to include")
    authors: Optional[List[str]] = None
    sentiment: Optional[str] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(12, ge=1, le=100)
    sort: str = Field("recent", pattern="^(recent|engagement)$")


class SosmedPost(BaseModel):
    id: str
    code: Optional[str] = None
    url: Optional[str] = None
    author: Optional[str] = None
    text: Optional[str] = None
    taken_at: Optional[str] = None
    scraped_at: Optional[str] = None
    keyword: Optional[str] = None
    likes: int = 0
    comments: int = 0
    reposts: int = 0
    quotes: int = 0
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    emotion: Optional[str] = None
    emotion_score: Optional[float] = None
    # Filled from threads_profiles when the scraper has seen the author.
    # Absent is normal: a post can be indexed before its author's profile is.
    author_avatar: Optional[str] = None
    author_name: Optional[str] = None
    author_verified: Optional[bool] = None
    author_followers: Optional[int] = None


class SosmedProfile(BaseModel):
    username: str
    full_name: Optional[str] = None
    biography: Optional[str] = None
    followers: Optional[int] = None
    following: Optional[int] = None
    is_verified: Optional[bool] = None
    profile_pic: Optional[str] = None
    bio_links: List[str] = []
    scraped_at: Optional[str] = None
    # Derived from the author's posts in this index, not from the profile doc
    post_count: int = 0
    total_likes: int = 0
    sentiment: List[dict] = []
    recent_posts: List["SosmedPost"] = []


class SosmedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[SosmedPost]


class SosmedAnalytics(BaseModel):
    total_posts: int
    annotated_posts: int
    engagement: dict
    sentiment: List[dict]
    emotion: List[dict]
    timeline: List[dict]
    top_authors: List[dict]
    top_keywords: List[dict]
    top_posts: List[SosmedPost]


def _index_for(platform: str) -> str:
    index = PLATFORM_INDEX.get((platform or "").lower())
    if not index:
        raise HTTPException(
            status_code=422,
            detail=f"platform belum didukung: {', '.join(PLATFORM_INDEX)}",
        )
    return index


def _query(filters: SosmedFilter) -> dict:
    must: list = []
    filter_clauses: list = []

    if filters.date_from or filters.date_to:
        # taken_at is when the post was published; scraped_at only says when we
        # happened to fetch it, which would group a backfill into one day.
        rng: dict = {}
        if filters.date_from:
            rng["gte"] = filters.date_from
        if filters.date_to:
            rng["lte"] = f"{filters.date_to}T23:59:59"
        filter_clauses.append({"range": {"taken_at": rng}})

    if filters.keywords:
        filter_clauses.append({"terms": {"keyword": filters.keywords}})
    if filters.authors:
        filter_clauses.append({"terms": {"author": filters.authors}})
    if filters.sentiment:
        filter_clauses.append({"term": {SENTIMENT_FIELD: filters.sentiment}})

    if not must:
        must = [{"match_all": {}}]
    return {"bool": {"must": must, "filter": filter_clauses}}


def _to_post(hit: dict) -> SosmedPost:
    src = hit["_source"]
    annotate = src.get("annotate") or {}
    sentiment = annotate.get("sentiment") or {}
    emotion = annotate.get("emotion") or {}
    return SosmedPost(
        id=hit["_id"],
        code=src.get("code"),
        url=src.get("url"),
        author=src.get("author"),
        text=src.get("text"),
        taken_at=str(src.get("taken_at")) if src.get("taken_at") is not None else None,
        scraped_at=str(src.get("scraped_at")) if src.get("scraped_at") is not None else None,
        keyword=src.get("keyword"),
        likes=src.get("likes") or 0,
        comments=src.get("comments") or 0,
        reposts=src.get("reposts") or 0,
        quotes=src.get("quotes") or 0,
        sentiment=sentiment.get("label"),
        sentiment_score=sentiment.get("score"),
        emotion=emotion.get("label"),
        emotion_score=emotion.get("score"),
    )


def _attach_profiles(posts: List[SosmedPost]) -> None:
    """Decorate posts with their author's profile, in one query per page.

    A missing profile leaves the fields None rather than failing the feed -
    the scraper indexes a post before it gets round to the author.
    """
    authors = sorted({p.author for p in posts if p.author})
    if not authors:
        return
    try:
        found = es_client.search(
            index=PROFILES_INDEX,
            body={"query": {"terms": {"username": authors}}, "size": len(authors)},
        )["hits"]["hits"]
    except Exception:
        return  # profiles are decoration; never let them break the feed

    by_name = {h["_source"].get("username"): h["_source"] for h in found}
    for post in posts:
        profile = by_name.get(post.author)
        if not profile:
            continue
        post.author_avatar = profile.get("profile_pic")
        post.author_name = profile.get("full_name")
        post.author_verified = profile.get("is_verified")
        post.author_followers = profile.get("followers")


# Only these hosts may be fetched. The URL comes out of Elasticsearch, so
# without an allowlist this endpoint would be an open proxy: anyone able to
# write a document could point it at an internal address.
AVATAR_HOSTS = (".fbcdn.net", ".cdninstagram.com")


@router.get("/avatar/{username}")
async def avatar(username: str):
    """Proxy an author's profile picture.

    Meta's CDN serves these fine server-to-server but refuses the browser when
    the page is on another origin, so a direct <img src> renders nothing.
    Deliberately unauthenticated: it is an <img> tag, which cannot carry an
    Authorization header, and it only ever returns pictures already scraped.
    """
    try:
        hits = es_client.search(
            index=PROFILES_INDEX,
            body={"query": {"term": {"username": username}}, "size": 1,
                  "_source": ["profile_pic"]},
        )["hits"]["hits"]
    except Exception:
        raise HTTPException(status_code=502, detail="Elasticsearch tidak bisa dihubungi")

    url = (hits[0]["_source"].get("profile_pic") if hits else None) or ""
    host = urlparse(url).hostname or ""
    if not url or not host.endswith(AVATAR_HOSTS):
        raise HTTPException(status_code=404, detail="Foto profil tidak tersedia")

    # A stale CDN signature comes back as 404 here, and the card falls back to
    # initials rather than leaving a hole.
    return await fetch_image(url)


@router.get("/profile/{username}", response_model=SosmedProfile)
async def get_profile(username: str, current_user: dict = Depends(get_current_active_user)):
    """Profile card: the scraped account plus what it has posted here."""
    try:
        hits = es_client.search(
            index=PROFILES_INDEX,
            body={"query": {"term": {"username": username}}, "size": 1},
        )["hits"]["hits"]

        stats = es_client.search(
            index=POSTS_INDEX,
            body={
                "query": {"term": {"author": username}},
                "size": 5,
                "sort": [{"taken_at": {"order": "desc"}}],
                "track_total_hits": True,
                "aggs": {
                    "likes": {"sum": {"field": "likes"}},
                    "sentiment": {"terms": {"field": SENTIMENT_FIELD, "size": 5}},
                },
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil profil: {str(e)}")

    post_count = stats["hits"]["total"]["value"]
    if not hits and post_count == 0:
        raise HTTPException(status_code=404, detail=f"@{username} belum pernah di-scrape")

    src = hits[0]["_source"] if hits else {}
    links = src.get("bio_links") or []
    return SosmedProfile(
        username=src.get("username") or username,
        full_name=src.get("full_name"),
        biography=src.get("biography"),
        followers=src.get("followers"),
        following=src.get("following"),
        is_verified=src.get("is_verified"),
        profile_pic=src.get("profile_pic"),
        bio_links=links if isinstance(links, list) else [links],
        scraped_at=str(src.get("scraped_at")) if src.get("scraped_at") is not None else None,
        post_count=post_count,
        total_likes=int(stats["aggregations"]["likes"]["value"]),
        sentiment=[
            {"label": b["key"], "count": b["doc_count"]}
            for b in stats["aggregations"]["sentiment"]["buckets"]
        ],
        recent_posts=[_to_post(h) for h in stats["hits"]["hits"]],
    )


@router.post("/search", response_model=SosmedResponse)
async def search_posts(filters: SosmedFilter, current_user: dict = Depends(get_current_active_user)):
    """Paginated post feed, newest first or most engaged first."""
    index = _index_for(filters.platform)
    sort = (
        [{"taken_at": {"order": "desc"}}]
        if filters.sort == "recent"
        # No single engagement field exists, so rank on the one that drives the
        # others; a script sort over four fields is not worth the cost here.
        else [{"likes": {"order": "desc"}}, {"taken_at": {"order": "desc"}}]
    )

    try:
        result = es_client.search(
            index=index,
            body={
                "query": _query(filters),
                "from": (filters.page - 1) * filters.page_size,
                "size": filters.page_size,
                "sort": sort,
                "track_total_hits": True,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil post: {str(e)}")

    total = result["hits"]["total"]["value"]
    items = [_to_post(h) for h in result["hits"]["hits"]]
    _attach_profiles(items)
    return SosmedResponse(
        total=total,
        page=filters.page,
        page_size=filters.page_size,
        total_pages=(total + filters.page_size - 1) // filters.page_size,
        items=items,
    )


@router.post("/analytics", response_model=SosmedAnalytics)
async def sosmed_analytics(filters: SosmedFilter, current_user: dict = Depends(get_current_active_user)):
    """Volume, sentiment, engagement and who is driving it."""
    index = _index_for(filters.platform)
    query = _query(filters)

    try:
        result = es_client.search(
            index=index,
            body={
                "query": query,
                "size": 0,
                "track_total_hits": True,
                "aggs": {
                    "annotated": {"filter": {"exists": {"field": "annotate.sentiment"}}},
                    "likes": {"sum": {"field": "likes"}},
                    "comments": {"sum": {"field": "comments"}},
                    "reposts": {"sum": {"field": "reposts"}},
                    "quotes": {"sum": {"field": "quotes"}},
                    "sentiment": {"terms": {"field": SENTIMENT_FIELD, "size": 5}},
                    "emotion": {"terms": {"field": EMOTION_FIELD, "size": 10}},
                    "authors": {
                        "terms": {"field": "author", "size": 10},
                        "aggs": {"likes": {"sum": {"field": "likes"}}},
                    },
                    "keywords": {"terms": {"field": "keyword", "size": 10}},
                    "timeline": {
                        "date_histogram": {
                            "field": "taken_at",
                            "calendar_interval": "day",
                            "min_doc_count": 0,
                            # Without this the bucket key comes back in the
                            # field's own mapping format - epoch_second - and
                            # the chart axis reads "1786665600".
                            "format": "yyyy-MM-dd",
                        },
                        "aggs": {
                            "negative": {"filter": {"term": {SENTIMENT_FIELD: "negatif"}}},
                            "likes": {"sum": {"field": "likes"}},
                        },
                    },
                },
            },
        )

        top = es_client.search(
            index=index,
            body={
                "query": query,
                "size": 5,
                "sort": [{"likes": {"order": "desc"}}],
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menghitung analitik: {str(e)}")

    aggs = result["aggregations"]
    annotated = aggs["annotated"]["doc_count"]

    def labelled(key: str) -> List[dict]:
        return [
            {
                "label": b["key"],
                "count": b["doc_count"],
                "percentage": round(b["doc_count"] / annotated * 100, 1) if annotated else 0.0,
            }
            for b in aggs[key]["buckets"]
        ]

    return SosmedAnalytics(
        total_posts=result["hits"]["total"]["value"],
        annotated_posts=annotated,
        engagement={
            "likes": int(aggs["likes"]["value"]),
            "comments": int(aggs["comments"]["value"]),
            "reposts": int(aggs["reposts"]["value"]),
            "quotes": int(aggs["quotes"]["value"]),
        },
        sentiment=labelled("sentiment"),
        emotion=labelled("emotion"),
        timeline=[
            {
                "date": b["key_as_string"],
                "count": b["doc_count"],
                "negative": b["negative"]["doc_count"],
                "likes": int(b["likes"]["value"]),
            }
            for b in aggs["timeline"]["buckets"]
        ],
        top_authors=[
            {"name": b["key"], "count": b["doc_count"], "likes": int(b["likes"]["value"])}
            for b in aggs["authors"]["buckets"]
        ],
        top_keywords=[{"name": b["key"], "count": b["doc_count"]} for b in aggs["keywords"]["buckets"]],
        top_posts=[_to_post(h) for h in top["hits"]["hits"]],
    )
