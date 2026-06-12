"""Pydantic V2 schemas for the Research Agent.

Organised in pipeline order:
  1. ResearchRequest     — what the user sends
  2. ScrapedPage         — raw scraper output (internal)
  3. PreprocessedContent — cleaned text for LLM (internal)
  4. CompanyProfile      — LLM extraction result
  5. CompetitorInfo      — lightweight competitor discovery
  6. TrendInfo           — lightweight trend discovery
  7. MarketingOpportunity — identified gaps/opportunities
  8. ResearchMetadata    — timing, model, version info
  9. ResearchOutput      — full result combining all of the above
  10. ResearchResponse   — API response wrapper (job_id + status + result)

Design rules:
  - Every schema uses model_config with strict=False so JSON round-trips cleanly.
  - Field descriptions are included so they double as LLM prompt hints when
    we serialise the schema for structured output.
  - Internal pipeline schemas (ScrapedPage, PreprocessedContent) are never
    exposed in API responses — they're used between services only.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, ConfigDict


# ── Enums ────────────────────────────────────────────────────────────────────


class JobStatus(str, Enum):
    """Research job lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ── API Input ────────────────────────────────────────────────────────────────


class ResearchRequest(BaseModel):
    """What the user submits to start a research job."""

    model_config = ConfigDict(str_strip_whitespace=True)

    company_url: HttpUrl = Field(
        description="The company's website URL to scrape and analyze."
    )
    company_name: str = Field(
        min_length=1,
        max_length=200,
        description="Name of the company being researched.",
    )
    industry: str | None = Field(
        default=None,
        max_length=100,
        description="Optional industry or business type hint (e.g., 'B2B SaaS', 'ecommerce').",
    )


# ── Internal Pipeline Schemas ────────────────────────────────────────────────


class ScrapedPage(BaseModel):
    """Raw output from scraping a single page. Internal use only."""

    url: str
    title: str = ""
    meta_description: str = ""
    headings: list[str] = Field(default_factory=list, description="H1-H3 text content")
    body_text: str = Field(default="", description="Cleaned paragraph/text content")
    links: list[str] = Field(
        default_factory=list, description="All href links found on the page"
    )
    scrape_timestamp: datetime = Field(default_factory=datetime.now)


class PreprocessedContent(BaseModel):
    """Cleaned and structured content ready for LLM analysis. Internal use only.

    This is the bridge between scraping (deterministic) and LLM reasoning.
    Everything here is plain text — no HTML, no noise.

    Content is organised into named sections by page type so the LLM
    receives structured, high-signal context instead of a raw dump.
    """

    company_name: str
    homepage_title: str = ""
    meta_description: str = ""

    # ── Structured sections (organised by page type) ─────────────────
    homepage_summary: str = Field(
        default="",
        description="Cleaned body text from the homepage — hero messaging, value props.",
    )
    about_section: str = Field(
        default="",
        description="Company story, mission, team — from the About page.",
    )
    products_section: str = Field(
        default="",
        description="Products, services, features — from the Products/Services page.",
    )
    pricing_section: str = Field(
        default="",
        description="Pricing signals, plan names, price points — from the Pricing page.",
    )
    contact_section: str = Field(
        default="",
        description="Contact info, office locations, support channels.",
    )

    # ── Aggregated fields ────────────────────────────────────────────
    all_headings: list[str] = Field(default_factory=list)
    key_value_propositions: list[str] = Field(
        default_factory=list,
        description="Hero headlines and strong value-prop sentences extracted from headings.",
    )
    body_text_combined: str = Field(
        default="",
        description="Deduplicated body text from all scraped pages, concatenated.",
    )
    internal_page_titles: list[str] = Field(
        default_factory=list,
        description="Titles of internal pages that were found (scraped or not).",
    )
    external_links: list[str] = Field(
        default_factory=list,
        description="Outbound links to other domains (potential partners/competitors).",
    )
    combined_context: str = Field(
        default="",
        description="Final LLM-ready context: all sections merged into a structured prompt block.",
    )
    word_count: int = 0



# ── LLM Output Schemas ──────────────────────────────────────────────────────


class CompanyProfile(BaseModel):
    """Core intelligence extracted about the company.

    The LLM produces this from preprocessed website content.
    Field descriptions are intentionally written as LLM instructions.
    """

    business_summary: str = Field(
        description="2-3 sentence summary of what the company does, who they serve, and their core value."
    )
    products_services: list[str] = Field(
        min_length=1,
        description="List of products, services, or offerings identified on the website.",
    )
    target_audience: list[str] = Field(
        min_length=1,
        description="Who the company is selling to — specific segments, not vague groups.",
    )
    brand_tone: list[str] = Field(
        description=(
            "3-5 adjectives describing the brand's communication style "
            "(e.g., 'professional', 'playful', 'technical', 'empathetic')."
        ),
    )
    usp: str = Field(
        description="The unique selling proposition — what makes this company different, in 1-2 sentences."
    )
    industry_category: str = Field(
        description="Industry classification (e.g., 'B2B SaaS', 'DTC ecommerce', 'Healthcare')."
    )


class CompetitorInfo(BaseModel):
    """A single discovered competitor. Lightweight — no deep analysis in V1."""

    name: str = Field(description="Competitor company name.")
    url: str | None = Field(
        default=None, description="Competitor website URL if discoverable."
    )
    similarity_reason: str = Field(
        description="Why this is considered a competitor (1 sentence)."
    )


class TrendInfo(BaseModel):
    """A single industry trend relevant to the company."""

    trend: str = Field(description="Brief description of the trend.")
    relevance: str = Field(
        description="Why this trend matters for the company's marketing (1 sentence)."
    )


class MarketingOpportunity(BaseModel):
    """A specific marketing gap or opportunity the company could exploit."""

    opportunity: str = Field(description="What the opportunity is.")
    priority: Literal["high", "medium", "low"] = Field(
        description="How impactful this opportunity could be."
    )
    reasoning: str = Field(
        description="Why this is an opportunity and what evidence supports it."
    )


# ── Metadata ─────────────────────────────────────────────────────────────────


class ResearchMetadata(BaseModel):
    """Operational metadata about the research run. For debugging and observability."""

    agent_version: str = "1.0.0"
    research_timestamp: datetime = Field(default_factory=datetime.now)
    pages_scraped: int = 0
    llm_model_used: str = ""
    total_tokens_used: int | None = None
    processing_time_seconds: float = 0.0


# ── Final Output ─────────────────────────────────────────────────────────────


class ResearchOutput(BaseModel):
    """Complete research result. Stored in DB as JSON and returned in API responses.

    This is what the Research Agent produces after the full pipeline:
    scrape → preprocess → LLM analysis → validation.
    """

    company_name: str
    company_url: str
    profile: CompanyProfile
    competitors: list[CompetitorInfo] = Field(default_factory=list)
    trends: list[TrendInfo] = Field(default_factory=list)
    opportunities: list[MarketingOpportunity] = Field(default_factory=list)
    metadata: ResearchMetadata = Field(default_factory=ResearchMetadata)


# ── API Response Wrapper ─────────────────────────────────────────────────────


class ResearchResponse(BaseModel):
    """API response for GET /api/v1/research/{job_id}.

    Wraps the job status and result together. The `result` field is None
    when the job is still pending/running, or when it failed.
    """

    job_id: str
    status: JobStatus
    company_name: str
    company_url: str
    result: ResearchOutput | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
