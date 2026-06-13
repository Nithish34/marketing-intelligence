"""Research Agent — pipeline orchestrator for company intelligence extraction.

Coordinates the scrape → preprocess → analyze pipeline into a single
``run_research()`` call.  This module contains NO intelligence, NO prompt
engineering, and NO business logic — it is pure orchestration.

Pipeline flow::

    static scrape
          ↓
    preprocess
          ↓
    quality check
          │
    good? ─── YES ──→ analyze → output
          │
          NO
          ↓
    headless scrape (fallback)
          ↓
    preprocess again
          ↓
    analyze → output

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
from app.services.headless_scraper import scrape_company_headless
from app.services.llm_client import analyze_company
from app.services.preprocessor import preprocess
from app.services.scraper import scrape_company

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quality thresholds — static extraction below these triggers headless fallback
# ---------------------------------------------------------------------------

LOW_WORD_COUNT_THRESHOLD: int = 500
WEAK_HOMEPAGE_THRESHOLD: int = 300
MIN_TOTAL_SIGNAL_THRESHOLD: int = 1000


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class ResearchError(RuntimeError):
    """Raised when scraping or preprocessing fails during research."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _scrape_static(url: str) -> list[ScrapedPage]:
    """Static scrape via httpx.  Returns empty list on failure (never raises)."""
    return await scrape_company(url)


async def _scrape_headless(url: str) -> list[ScrapedPage]:
    """Headless browser scrape via Playwright.  Never raises."""
    try:
        return await scrape_company_headless(url)
    except Exception as exc:
        logger.warning("Headless scrape failed for %s: %s", url, exc)
        return []


def _preprocess(pages: list[ScrapedPage], company_name: str) -> PreprocessedContent:
    """Clean and structure raw pages for LLM consumption."""
    content = preprocess(pages, company_name)
    logger.info(
        "Preprocessed content for %s: %d words",
        company_name,
        content.word_count,
    )
    return content


def _should_retry_headless(word_count: int, homepage_chars: int) -> bool:
    """Determine if fallback to headless scraper is needed based on static signal quality."""
    return (
        word_count < LOW_WORD_COUNT_THRESHOLD
        or (
            homepage_chars < WEAK_HOMEPAGE_THRESHOLD
            and word_count < MIN_TOTAL_SIGNAL_THRESHOLD
        )
    )


BLOCK_PATTERNS: list[str] = [
    "just a moment",
    "checking your browser",
    "verify you are human",
    "cloudflare",
]


def _contains_bot_protection(pages: list[ScrapedPage]) -> bool:
    """Check if any of the scraped pages contain bot-protection/blocking patterns."""
    for page in pages:
        title_lower = page.title.lower()
        body_lower = page.body_text.lower()
        for pattern in BLOCK_PATTERNS:
            if pattern in title_lower or pattern in body_lower:
                return True
    return False


def _log_extraction_quality(
    method: str,
    company_name: str,
    pages: list[ScrapedPage],
    content: PreprocessedContent,
) -> None:
    """Log extraction statistics for debugging."""
    logger.info(
        "%s extraction for %s: pages=%d, words=%d, homepage_chars=%d",
        method.capitalize(),
        company_name,
        len(pages),
        content.word_count,
        len(content.homepage_summary),
    )


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
        If both static and headless scraping fail to produce usable content.
    LLMClientError (and subclasses)
        If Gemini analysis fails.
    """
    company_name = request.company_name
    url = str(request.company_url)

    logger.info("Starting research for %s (%s)", company_name, url)

    # 1. Static scrape
    pages = await _scrape_static(url)
    preprocessed = _preprocess(pages, company_name)
    _log_extraction_quality("static", company_name, pages, preprocessed)

    # 2. Headless fallback if quality is low
    if _should_retry_headless(preprocessed.word_count, len(preprocessed.homepage_summary)) or len(pages) == 0:
        logger.info(
            "Low quality extraction:\nwords=%d\nhomepage_chars=%d\nretrying headless",
            preprocessed.word_count,
            len(preprocessed.homepage_summary),
        )
        headless_pages = await _scrape_headless(url)

        if headless_pages:
            if _contains_bot_protection(headless_pages):
                logger.warning("Bot protection detected. Discarding headless result.")
            else:
                headless_preprocessed = _preprocess(headless_pages, company_name)
                _log_extraction_quality(
                    "headless", company_name, headless_pages, headless_preprocessed,
                )

                # Use headless result if it produced better content
                if headless_preprocessed.word_count > preprocessed.word_count:
                    logger.info(
                        "Headless result is better for %s: %d -> %d words",
                        company_name,
                        preprocessed.word_count,
                        headless_preprocessed.word_count,
                    )
                    pages = headless_pages
                    preprocessed = headless_preprocessed
                else:
                    logger.info(
                        "Static result was better for %s, keeping it",
                        company_name,
                    )

    # 3. Final gate — never continue with zero pages
    if not pages:
        raise ResearchError(
            f"No pages scraped from {url}. "
            "Both static and headless scraping failed. "
            "The site may be unreachable or blocking automated access."
        )

    # 4. Analyze
    profile, model_used, latency = await _analyze(preprocessed)

    # 5. Build output
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

    # 6. Debug snapshot (non-critical)
    _save_snapshot_safe(result, preprocessed, model_used, latency)

    logger.info(
        "Research complete for %s: pages=%d, model=%s, time=%.2fs",
        company_name,
        len(pages),
        model_used,
        latency,
    )

    return result
