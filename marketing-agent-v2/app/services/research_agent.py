"""Research Agent — pipeline orchestrator for company intelligence extraction.

Coordinates the scrape → preprocess → analyze pipeline into a single
``run_research()`` call.  This module contains NO intelligence, NO prompt
engineering, and NO business logic — it is pure orchestration.

Public API::

    result = await run_research(request)
    # result is a validated ResearchOutput
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from app.config import settings
from app.schemas.research import (
    CompanyProfile,
    PreprocessedContent,
    ResearchMetadata,
    ResearchOutput,
    ResearchRequest,
    ScrapedPage,
)
from app.services.debug_persistence import save_debug_snapshot
from app.services.llm_client import analyze_company
from app.services.preprocessor import preprocess
from app.services.scraper import scrape_company

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ResearchError(RuntimeError):
    """Raised when scraping or preprocessing fails during research."""


# ---------------------------------------------------------------------------
# Private helpers — each wraps exactly one service call
# ---------------------------------------------------------------------------


async def _scrape(url: str) -> list[ScrapedPage]:
    """Scrape the company website.  Raises on empty result."""
    pages = await scrape_company(url)

    if not pages:
        raise ResearchError(
            f"No pages scraped from {url}. The site may be unreachable, "
            "blocked by robots.txt, or returning non-HTML content."
        )

    logger.info("Scraped %d pages from %s", len(pages), url)
    return pages


def _preprocess(pages: list[ScrapedPage], company_name: str) -> PreprocessedContent:
    """Clean and structure raw pages for LLM consumption."""
    content = preprocess(pages, company_name)
    logger.info(
        "Preprocessed content for %s: %d words",
        company_name,
        content.word_count,
    )
    return content


async def _analyze(content: PreprocessedContent) -> tuple[CompanyProfile, str, float]:
    """Run Gemini analysis.  Returns (profile, model_used, latency_seconds)."""
    model = settings.gemini_model
    start = time.perf_counter()
    profile = await analyze_company(content)
    latency = time.perf_counter() - start

    logger.info(
        "Gemini analysis complete: model=%s, latency=%.2fs",
        model,
        latency,
    )
    return profile, model, latency


def _build_metadata(
    pages_scraped: int,
    model_used: str,
    processing_time_seconds: float,
) -> ResearchMetadata:
    """Construct ResearchMetadata from pipeline results."""
    return ResearchMetadata(
        agent_version=settings.app_version,
        research_timestamp=datetime.now(),
        pages_scraped=pages_scraped,
        llm_model_used=model_used,
        processing_time_seconds=round(processing_time_seconds, 2),
    )


def _save_snapshot_safe(
    output: ResearchOutput,
    preprocessed: PreprocessedContent,
    model_used: str,
    processing_time: float,
) -> None:
    """Persist a debug snapshot.  Never raises — failures are logged and swallowed."""
    try:
        path = save_debug_snapshot(
            company_name=output.company_name,
            company_url=output.company_url,
            company_profile=output.profile,
            preprocessed_context=preprocessed.combined_context,
            word_count=preprocessed.word_count,
            model_used=model_used,
            processing_time_seconds=processing_time,
            pages_scraped=output.metadata.pages_scraped,
            prompt_version="v2",
            metadata=output.metadata,
        )
        logger.info("Debug snapshot saved to %s", path)
    except Exception:
        logger.warning(
            "Failed to save debug snapshot for %s — research result is unaffected",
            output.company_name,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_research(request: ResearchRequest) -> ResearchOutput:
    """Execute the full research pipeline for a single company.

    Parameters
    ----------
    request:
        A ``ResearchRequest`` with ``company_name`` and ``company_url``.

    Returns
    -------
    ResearchOutput
        Validated research result containing the company profile and metadata.

    Raises
    ------
    ResearchError
        If scraping or preprocessing fails.
    LLMClientError (and subclasses)
        If Gemini analysis fails.
    """
    company_name = request.company_name
    url = str(request.company_url)

    logger.info("Starting research for %s (%s)", company_name, url)

    # 1. Scrape
    pages = await _scrape(url)

    # 2. Preprocess
    preprocessed = _preprocess(pages, company_name)

    # 3. Analyze
    profile, model_used, latency = await _analyze(preprocessed)

    # 4. Build output
    metadata = _build_metadata(
        pages_scraped=len(pages),
        model_used=model_used,
        processing_time_seconds=latency,
    )

    result = ResearchOutput(
        company_name=company_name,
        company_url=url,
        profile=profile,
        metadata=metadata,
    )

    # 5. Debug snapshot (non-critical)
    _save_snapshot_safe(result, preprocessed, model_used, latency)

    logger.info(
        "Research complete for %s: pages=%d, model=%s, time=%.2fs",
        company_name,
        len(pages),
        model_used,
        latency,
    )

    return result
