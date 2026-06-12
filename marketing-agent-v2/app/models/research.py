"""SQLAlchemy Core table definition for research jobs.

One table for V1. Stores the full ResearchOutput as a JSON blob in result_json.
No normalized columns for individual fields — that's a premature optimization
when you're querying by job_id 99% of the time.

If you later need to query "all companies in SaaS industry", add an index on a
new `industry` column. Don't pre-build columns you aren't querying.
"""

from __future__ import annotations

import sqlalchemy as sa

# Shared metadata object — database.create_tables() calls metadata.create_all()
metadata = sa.MetaData()

research_jobs = sa.Table(
    "research_jobs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),          # UUID as string
    sa.Column("company_name", sa.String(200), nullable=False),
    sa.Column("company_url", sa.Text, nullable=False),
    sa.Column("industry", sa.String(100), nullable=True),
    sa.Column(
        "status",
        sa.String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    ),
    sa.Column("result_json", sa.Text, nullable=True),           # Full ResearchOutput
    sa.Column("error_message", sa.Text, nullable=True),
    sa.Column("created_at", sa.String(30), nullable=False),     # ISO 8601
    sa.Column("completed_at", sa.String(30), nullable=True),    # ISO 8601
    sa.Column("pages_scraped", sa.Integer, default=0, server_default="0"),
    sa.Column("processing_time_seconds", sa.Float, nullable=True),
)
