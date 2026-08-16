"""Reporting: an on-screen summary of a period, and the same data as a file.

Both endpoints read the annotations the annotator pipeline writes into
`annotate`, so a document the pipeline has not reached yet simply does not
appear in the sentiment/emotion counts.
"""
import csv
import io
from collections import Counter
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_active_user
from app.core.config import settings
from app.core.elasticsearch import es_client
from app.services.keyword_service import keyword_service

router = APIRouter(prefix="/reports", tags=["Reports"])

# Same mapping the NER explorer uses: this model tags locations GPE, and the
# remaining groups (dates, numbers, products) are not useful in a report.
ENTITY_GROUPS = {
    "PER": "people",
    "ORG": "organizations", "NOR": "organizations", "ORGANIZATION": "organizations",
    "LOC": "locations", "GPE": "locations",
}

# One page of articles in the export. Enough for a monthly report without
# holding an unbounded result set in memory.
MAX_EXPORT_ARTICLES = 1000


class ReportFilter(BaseModel):
    date_from: str = Field(..., description="Start date (YYYY-MM-DD)")
    date_to: str = Field(..., description="End date (YYYY-MM-DD)")
    sources: Optional[List[str]] = None
    sentiment: Optional[str] = None


class LabelCount(BaseModel):
    label: str
    count: int
    percentage: float


class NamedCount(BaseModel):
    name: str
    count: int


class ReportSummary(BaseModel):
    date_from: str
    date_to: str
    keywords: List[str]
    total_articles: int
    annotated_articles: int
    sentiment: List[LabelCount]
    emotion: List[LabelCount]
    top_sources: List[NamedCount]
    people: List[NamedCount]
    organizations: List[NamedCount]
    locations: List[NamedCount]


async def _build_query(filters: ReportFilter, user_id: int):
    """Date range + the user's keywords, plus the optional facet filters."""
    keyword_data = await keyword_service.get_user_keywords(user_id)
    keywords = (keyword_data or {}).get("keywords", []) or []
    operator = (keyword_data or {}).get("operator", "OR") or "OR"

    must: list = [{
        "range": {"scraped_at": {"gte": filters.date_from, "lte": f"{filters.date_to}T23:59:59"}}
    }]
    filter_clauses: list = []

    if keywords:
        matches = [{"multi_match": {"query": k, "fields": ["title^3", "body"], "type": "best_fields"}}
                   for k in keywords]
        if operator.upper() == "AND":
            must.extend(matches)
        else:
            filter_clauses.append({"bool": {"should": matches, "minimum_should_match": 1}})

    if filters.sources:
        filter_clauses.append({"terms": {"source_name": filters.sources}})
    if filters.sentiment:
        filter_clauses.append({"term": {"annotate.sentiment.label.keyword": filters.sentiment}})

    return {"bool": {"must": must, "filter": filter_clauses}}, keywords


def _percentages(buckets, total) -> List[LabelCount]:
    return [
        LabelCount(
            label=b["key"],
            count=b["doc_count"],
            percentage=round(b["doc_count"] / total * 100, 1) if total else 0.0,
        )
        for b in buckets
    ]


async def _summarise(filters: ReportFilter, user_id: int) -> ReportSummary:
    query, keywords = await _build_query(filters, user_id)

    result = es_client.search(
        index=settings.ELASTICSEARCH_INDEX,
        body={
            "query": query,
            "size": 0,
            "aggs": {
                "annotated": {"filter": {"exists": {"field": "annotate.sentiment"}}},
                "sentiment": {"terms": {"field": "annotate.sentiment.label.keyword", "size": 5}},
                "emotion": {"terms": {"field": "annotate.emotion.label.keyword", "size": 10}},
                "sources": {"terms": {"field": "source_name", "size": 10}},
            },
        },
    )

    aggs = result["aggregations"]
    total = result["hits"]["total"]["value"]
    annotated = aggs["annotated"]["doc_count"]

    # Entities are paired in Python rather than aggregated: `annotate.entities`
    # is a plain object array, so Elasticsearch flattens it and an aggregation
    # would mix a document's words across its entity groups.
    entity_hits = es_client.search(
        index=settings.ELASTICSEARCH_INDEX,
        body={"query": query, "size": 500, "_source": ["annotate.entities"]},
    )
    counters = {k: Counter() for k in ("people", "organizations", "locations")}
    for doc in entity_hits["hits"]["hits"]:
        for ent in (doc["_source"].get("annotate") or {}).get("entities") or []:
            bucket = ENTITY_GROUPS.get((ent.get("entity_group") or "").upper())
            word = (ent.get("word") or "").strip()
            if bucket and len(word) > 1:
                counters[bucket][word] += 1

    return ReportSummary(
        date_from=filters.date_from,
        date_to=filters.date_to,
        keywords=keywords,
        total_articles=total,
        annotated_articles=annotated,
        sentiment=_percentages(aggs["sentiment"]["buckets"], annotated),
        emotion=_percentages(aggs["emotion"]["buckets"], annotated),
        top_sources=[NamedCount(name=b["key"], count=b["doc_count"]) for b in aggs["sources"]["buckets"]],
        people=[NamedCount(name=n, count=c) for n, c in counters["people"].most_common(10)],
        organizations=[NamedCount(name=n, count=c) for n, c in counters["organizations"].most_common(10)],
        locations=[NamedCount(name=n, count=c) for n, c in counters["locations"].most_common(10)],
    )


@router.post("/summary", response_model=ReportSummary)
async def get_report_summary(
    filters: ReportFilter,
    current_user: dict = Depends(get_current_active_user),
):
    """Period summary: volume, sentiment/emotion split, top sources and entities."""
    try:
        return await _summarise(filters, current_user["id"])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to build report summary: {str(e)}",
        )


async def _fetch_articles(filters: ReportFilter, user_id: int):
    query, _ = await _build_query(filters, user_id)
    result = es_client.search(
        index=settings.ELASTICSEARCH_INDEX,
        body={
            "query": query,
            "size": MAX_EXPORT_ARTICLES,
            "sort": [{"scraped_at": {"order": "desc"}}],
            "_source": ["title", "source_name", "url", "author", "published_at",
                        "scraped_at", "annotate.sentiment", "annotate.emotion"],
        },
    )
    return [h["_source"] for h in result["hits"]["hits"]]


@router.post("/export/csv")
async def export_csv(
    filters: ReportFilter,
    current_user: dict = Depends(get_current_active_user),
):
    """Article list as CSV. Opens directly in Excel and Google Sheets."""
    try:
        articles = await _fetch_articles(filters, current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export: {str(e)}")

    buffer = io.StringIO()
    # utf-8-sig further down: without the BOM Excel on Windows renders
    # Indonesian accented characters as mojibake.
    writer = csv.writer(buffer)
    writer.writerow(["title", "source", "sentiment", "sentiment_score",
                     "emotion", "emotion_score", "author", "published_at", "url"])
    for a in articles:
        annotate = a.get("annotate") or {}
        sentiment = annotate.get("sentiment") or {}
        emotion = annotate.get("emotion") or {}
        writer.writerow([
            a.get("title", ""), a.get("source_name", ""),
            sentiment.get("label", ""), round(sentiment["score"], 4) if sentiment.get("score") else "",
            emotion.get("label", ""), round(emotion["score"], 4) if emotion.get("score") else "",
            a.get("author", ""), a.get("published_at") or a.get("scraped_at", ""), a.get("url", ""),
        ])

    filename = f"medmon-report-{filters.date_from}-to-{filters.date_to}.csv"
    return StreamingResponse(
        io.BytesIO(buffer.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/pdf")
async def export_pdf(
    filters: ReportFilter,
    current_user: dict = Depends(get_current_active_user),
):
    """Summary plus the article list as a PDF."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate,
                                        Spacer, Table, TableStyle)
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF export needs reportlab: pip install -r requirements.txt",
        )

    try:
        summary = await _summarise(filters, current_user["id"])
        articles = await _fetch_articles(filters, current_user["id"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export: {str(e)}")

    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title="Media Monitoring Report",
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)

    def table(rows, widths):
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ]))
        return t

    story = [
        Paragraph("Media Monitoring Report", styles["Title"]),
        Paragraph(f"Periode {summary.date_from} s/d {summary.date_to}", styles["Normal"]),
        Paragraph(f"Kata kunci: {', '.join(summary.keywords) or '-'}", styles["Normal"]),
        Paragraph(f"Dibuat {datetime.now():%d %b %Y %H:%M}", styles["Normal"]),
        Spacer(1, 8 * mm),
        Paragraph(
            f"Total artikel: <b>{summary.total_articles}</b> &nbsp;&nbsp; "
            f"Sudah dianotasi: <b>{summary.annotated_articles}</b>",
            styles["Normal"]),
        Spacer(1, 6 * mm),
    ]

    def label_section(title, rows):
        story.append(Paragraph(title, styles["Heading3"]))
        if rows:
            story.append(table([["Label", "Jumlah", "%"]] +
                               [[r.label, str(r.count), f"{r.percentage}%"] for r in rows],
                               [70 * mm, 25 * mm, 25 * mm]))
        else:
            story.append(Paragraph("Tidak ada data", styles["Normal"]))
        story.append(Spacer(1, 5 * mm))

    label_section("Sentiment", summary.sentiment)
    label_section("Emotion", summary.emotion)

    def name_section(title, rows):
        story.append(Paragraph(title, styles["Heading3"]))
        if rows:
            story.append(table([["Nama", "Jumlah"]] + [[r.name, str(r.count)] for r in rows],
                               [95 * mm, 25 * mm]))
        else:
            story.append(Paragraph("Tidak ada data", styles["Normal"]))
        story.append(Spacer(1, 5 * mm))

    name_section("Sumber teratas", summary.top_sources)
    name_section("Tokoh", summary.people)
    name_section("Organisasi", summary.organizations)
    name_section("Lokasi", summary.locations)

    story.append(PageBreak())
    story.append(Paragraph(f"Daftar Artikel ({len(articles)})", styles["Heading2"]))
    story.append(Spacer(1, 4 * mm))

    rows = [["Judul", "Sumber", "Sentiment", "Emotion", "Tanggal"]]
    for a in articles[:200]:  # a 1000-row PDF helps nobody; CSV carries the rest
        annotate = a.get("annotate") or {}
        published = (a.get("published_at") or a.get("scraped_at") or "")[:10]
        rows.append([
            Paragraph((a.get("title") or "")[:150], styles["BodyText"]),
            a.get("source_name", ""),
            (annotate.get("sentiment") or {}).get("label", "-"),
            (annotate.get("emotion") or {}).get("label", "-"),
            published,
        ])
    story.append(table(rows, [85 * mm, 25 * mm, 20 * mm, 20 * mm, 20 * mm]))

    doc.build(story)
    buffer.seek(0)
    filename = f"medmon-report-{filters.date_from}-to-{filters.date_to}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
