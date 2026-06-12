"""Smoke test: verify database table creation and schema imports."""
import sys
import asyncio

sys.path.insert(0, "marketing agent v2")

from app.database import create_tables, get_db, close_db
from sqlalchemy import text


async def test():
    # Create tables
    await create_tables()
    print("Tables created OK")

    # Verify table exists and check columns
    async with get_db() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        )
        tables = result.fetchall()
        print(f"Tables in DB: {[r[0] for r in tables]}")

        result2 = await conn.execute(text("PRAGMA table_info(research_jobs)"))
        cols = result2.fetchall()
        print(f"Columns ({len(cols)}): {[r[1] for r in cols]}")

    await close_db()
    print("Shutdown OK")


asyncio.run(test())
