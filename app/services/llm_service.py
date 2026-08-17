"""LLM narrative summaries via the user's OpenAI-compatible gateway.

Configured entirely from the environment so the model can be swapped without
touching code. Nothing here runs on the homelab GPUs - the gateway does the
work, unlike the annotation models.
"""
from typing import List, Optional

import httpx

from app.core.config import settings

BASE_URL = settings.LLM_BASE_URL
MODEL = settings.LLM_MODEL
API_KEY = settings.LLM_API_KEY
TIMEOUT = settings.LLM_TIMEOUT

# Enough coverage to characterise a period without paying for a whole corpus.
MAX_ARTICLES = settings.LLM_MAX_ARTICLES

PROMPT = """Kamu analis media monitoring Indonesia. Ringkas liputan berikut jadi 3-4 kalimat bahasa Indonesia.

Sebutkan: isu utama yang muncul, arah sentimennya, dan aktor/lembaga yang paling sering disebut.
Jangan mengarang fakta di luar daftar. Jangan pakai bullet, tulis paragraf mengalir.

Periode: {period}
Total artikel: {total} (sentimen: {sentiment})

Judul artikel:
{titles}"""


class LLMNotConfigured(RuntimeError):
    pass


async def complete(prompt: str, max_tokens: int = 400) -> str:
    """Single-turn completion. The prompt is built by the caller."""
    if not API_KEY:
        raise LLMNotConfigured("LLM_API_KEY is not set")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                # Explicit: the gateway streams Server-Sent Events when `stream`
                # is omitted, and response.json() then fails on the SSE body.
                "stream": False,
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
        )
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"].strip()


async def summarise(period: str, total: int, sentiment: dict, titles: List[str]) -> str:
    if not API_KEY:
        raise LLMNotConfigured("LLM_API_KEY is not set")

    prompt = PROMPT.format(
        period=period,
        total=total,
        sentiment=", ".join(f"{k} {v}" for k, v in sentiment.items()) or "belum dianotasi",
        titles="\n".join(f"- {t}" for t in titles[:MAX_ARTICLES]),
    )

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                # Explicit: the gateway streams Server-Sent Events when `stream`
                # is omitted, and response.json() then fails on the SSE body.
                "stream": False,
                "max_tokens": 400,
                "temperature": 0.3,
            },
        )
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"].strip()


def model_name() -> Optional[str]:
    return MODEL if API_KEY else None
