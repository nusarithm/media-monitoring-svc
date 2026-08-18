"""LLM readings of the numbers other endpoints already produce.

Nothing here computes anything new: it takes a graph or a dashboard summary
and asks the model to say what it means, then caches the answer so opening a
page twice does not bill two calls.
"""
import hashlib
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_active_user
from app.core.database import execute, fetch_one
from app.services import llm_service

router = APIRouter(prefix="/insights", tags=["Insights"])


class GraphNode(BaseModel):
    id: str
    label: Optional[str] = None
    weight: int = 0
    degree: int = 0
    group: Optional[str] = None


class GraphEdge(BaseModel):
    source: str
    target: str
    value: int = 1


class GraphAnalysisRequest(BaseModel):
    date_from: str
    date_to: str
    nodes: List[GraphNode]
    edges: List[GraphEdge] = []
    refresh: bool = False


class DashboardAnalysisRequest(BaseModel):
    date_from: str
    date_to: str
    sources: Optional[List[str]] = None
    sentiment: Optional[str] = None
    refresh: bool = False


class Insight(BaseModel):
    text: str
    model: Optional[str] = None
    cached: bool


GRAPH_PROMPT = """Kamu analis media monitoring Indonesia. Di bawah ini jaringan entitas dari pemberitaan: siapa/apa yang paling sering disebut, dan pasangan yang sering muncul bersama.

Jelaskan dalam 3-4 kalimat bahasa Indonesia: aktor atau lembaga yang jadi pusat perhatian, kelompok keterkaitan yang menonjol, dan apa yang kemungkinan sedang jadi isu. Jangan mengarang fakta di luar data. Tulis paragraf mengalir, tanpa bullet.

Periode: {period}

Entitas teratas (nama, jumlah penyebutan, tipe):
{nodes}

Pasangan yang sering muncul bersama (A - B, jumlah artikel):
{edges}"""

DASHBOARD_PROMPT = """Kamu analis media monitoring Indonesia. Di bawah ini ringkasan angka pemberitaan satu periode.

Tulis 3-4 kalimat bahasa Indonesia: kondisi umum liputan, arah sentimen dan apa yang mungkin mendorongnya, media dan aktor yang paling menonjol. Jangan mengarang fakta di luar angka ini. Paragraf mengalir, tanpa bullet.

Periode: {period}
Total artikel: {total}
Sentimen: {sentiment}
Emosi: {emotion}
Media teratas: {sources}
Entitas teratas: {entities}"""


async def _cached(user_id: int, kind: str, payload: str, date_from: str, date_to: str,
                  prompt: str, refresh: bool) -> Insight:
    """One cache row per (user, kind, period, payload fingerprint).

    The fingerprint matters: the same period with different filters is a
    different question, and returning the first answer would be wrong.
    """
    from datetime import date as date_type

    fingerprint = hashlib.sha256(f"{kind}|{payload}".encode()).hexdigest()[:32]
    # daily_summaries already stores exactly this shape; topic_id is unused for
    # narratives so it carries the fingerprint instead of adding a table.
    cache_key = f"{kind}:{fingerprint}"

    if not refresh:
        row = await fetch_one(
            """
            SELECT summary, model FROM daily_summaries
             WHERE user_id = $1 AND model_key = $2 AND date_from = $3 AND date_to = $4
            """,
            user_id, cache_key, date_type.fromisoformat(date_from), date_type.fromisoformat(date_to),
        )
        if row:
            return Insight(text=row["summary"], model=row["model"], cached=True)

    try:
        text = await llm_service.complete(prompt)
    except llm_service.LLMNotConfigured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="LLM belum dikonfigurasi: set LLM_API_KEY di .env",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM gateway error: {str(e)[:200]}")

    await execute(
        """
        INSERT INTO daily_summaries (user_id, model_key, date_from, date_to, summary, model, article_count)
        VALUES ($1, $2, $3, $4, $5, $6, 0)
        -- The unique index is partial, so the predicate has to be repeated
        -- here or Postgres cannot match it to an arbiter.
        ON CONFLICT (user_id, model_key, date_from, date_to) WHERE model_key IS NOT NULL DO UPDATE
            SET summary = EXCLUDED.summary, model = EXCLUDED.model, created_at = NOW()
        """,
        user_id, cache_key, date_type.fromisoformat(date_from), date_type.fromisoformat(date_to),
        text, llm_service.model_name(),
    )
    return Insight(text=text, model=llm_service.model_name(), cached=False)


@router.post("/graph", response_model=Insight)
async def analyse_graph(body: GraphAnalysisRequest, current_user: dict = Depends(get_current_active_user)):
    """Read the entity network back in plain language."""
    if not body.nodes:
        raise HTTPException(status_code=400, detail="Graph kosong, tidak ada yang bisa dianalisa")

    # Only the strongest signals go to the model: 50 nodes and 700 edges would
    # bury the answer and cost tokens for noise.
    nodes = sorted(body.nodes, key=lambda n: -n.weight)[:20]
    edges = sorted(body.edges, key=lambda e: -e.value)[:25]

    prompt = GRAPH_PROMPT.format(
        period=f"{body.date_from} s/d {body.date_to}",
        nodes="\n".join(f"- {n.label or n.id} ({n.weight}, {n.group or 'lain'})" for n in nodes),
        edges="\n".join(f"- {e.source} - {e.target} ({e.value})" for e in edges) or "-",
    )
    payload = json.dumps([[n.id, n.weight] for n in nodes], sort_keys=True)
    return await _cached(current_user["id"], "graph", payload, body.date_from, body.date_to, prompt, body.refresh)


@router.post("/dashboard", response_model=Insight)
async def analyse_dashboard(body: DashboardAnalysisRequest, current_user: dict = Depends(get_current_active_user)):
    """Plain-language reading of the dashboard numbers.

    The figures are computed here rather than sent by the browser. The page had
    only its article count and the source filter to hand, so the model was
    asked to explain a period it was told nothing about - "Sentimen: belum ada"
    - and answered accordingly. This runs the same aggregation the report page
    uses, so the prose describes real numbers.
    """
    from app.api.reports import ReportFilter, _summarise

    try:
        summary = await _summarise(
            ReportFilter(
                date_from=body.date_from,
                date_to=body.date_to,
                sources=body.sources,
                sentiment=body.sentiment,
            ),
            current_user["id"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil angka: {str(e)}")

    if summary.total_articles == 0:
        raise HTTPException(status_code=404, detail="Tidak ada artikel di periode ini")

    entities = (summary.people + summary.organizations + summary.locations)
    entities.sort(key=lambda e: -e.count)

    prompt = DASHBOARD_PROMPT.format(
        period=f"{body.date_from} s/d {body.date_to}",
        total=f"{summary.total_articles} ({summary.annotated_articles} sudah dianotasi)",
        sentiment=", ".join(f"{s.label} {s.count}" for s in summary.sentiment) or "belum ada",
        emotion=", ".join(f"{e.label} {e.count}" for e in summary.emotion) or "belum ada",
        sources=", ".join(f"{s.name} {s.count}" for s in summary.top_sources[:8]) or "-",
        entities=", ".join(f"{e.name} {e.count}" for e in entities[:12]) or "-",
    )
    payload = json.dumps(
        {
            "t": summary.total_articles,
            "s": {s.label: s.count for s in summary.sentiment},
            "src": [s.name for s in summary.top_sources[:8]],
        },
        sort_keys=True,
    )
    return await _cached(current_user["id"], "dashboard", payload, body.date_from, body.date_to, prompt, body.refresh)
