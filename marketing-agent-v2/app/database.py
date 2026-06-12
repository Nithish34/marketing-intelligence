"""SQLite database setup with async support.

Uses SQLAlchemy Core (not ORM) with aiosqlite for async access.
Tables are created on startup via create_tables(). No Alembic yet — one table
doesn't justify a migration framework.

Usage:
    from app.database import get_db, create_tables

    # In FastAPI lifespan:
    await create_tables()

    # In route handlers:
    async with get_db() as db:
        await db.execute(...)
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncConnection

from app.config import settings


# ── Engine (lazy singleton) ──────────────────────────────────────────────────

_engine: AsyncEngine | None = None


def _get_engine() -> AsyncEngine:
    """Return the async SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        db_url = settings.effective_database_url

        # Ensure the data/ directory exists for SQLite
        if "sqlite" in db_url:
            # Extract the file path from the URL.
            # Format: sqlite+aiosqlite:///C:/path/to/file.db
            db_file = db_url.split("///", 1)[-1]
            Path(db_file).parent.mkdir(parents=True, exist_ok=True)

        _engine = create_async_engine(
            db_url,
            echo=settings.debug,  # log SQL when DEBUG=true
            # SQLite-specific: allow the same connection across threads.
            # Safe because we serialize writes through a single engine.
            connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
        )
    return _engine


# ── Table Creation ───────────────────────────────────────────────────────────

async def create_tables() -> None:
    """Create all tables defined in app.models. Call once on startup."""
    from app.models.research import metadata  # noqa: F811 — import here to avoid circular deps

    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


# ── Connection Context Manager ───────────────────────────────────────────────

@contextlib.asynccontextmanager
async def get_db():
    """Yield an async connection. Auto-commits on success, rolls back on error.

    Usage:
        async with get_db() as conn:
            await conn.execute(text("SELECT 1"))
    """
    engine = _get_engine()
    async with engine.begin() as conn:
        yield conn


# ── Shutdown ─────────────────────────────────────────────────────────────────

async def close_db() -> None:
    """Dispose of the engine. Call on app shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
