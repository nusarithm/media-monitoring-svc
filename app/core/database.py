"""PostgreSQL access layer.

One asyncpg pool for the whole app. The helpers return plain dicts so callers
keep working with the same shape the previous REST client returned.
"""
import asyncpg
from typing import Any, Dict, List, Optional
from app.core.config import settings


_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> None:
    """Create the connection pool. Called once from the app lifespan."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            command_timeout=settings.DB_COMMAND_TIMEOUT,
        )


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError(
            "Database pool is not initialized. init_pool() must run at app startup."
        )
    return _pool


async def fetch_one(sql: str, *args: Any) -> Optional[Dict[str, Any]]:
    """Return the first row as a dict, or None."""
    row = await get_pool().fetchrow(sql, *args)
    return dict(row) if row is not None else None


async def fetch_all(sql: str, *args: Any) -> List[Dict[str, Any]]:
    """Return all rows as a list of dicts."""
    rows = await get_pool().fetch(sql, *args)
    return [dict(row) for row in rows]


async def execute(sql: str, *args: Any) -> str:
    """Run a statement, return the command tag (e.g. 'UPDATE 1')."""
    return await get_pool().execute(sql, *args)
