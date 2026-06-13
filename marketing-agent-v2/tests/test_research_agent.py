"""Tests for the Research Agent pipeline orchestrator.

All external services are mocked.  These tests verify orchestration logic,
error propagation, and the mandatory rule that debug persistence failures
never kill research.

Note: FAKE_PREPROCESSED uses word_count=600 and a long homepage_summary
to stay above the headless fallback quality thresholds (MIN_WORD_COUNT=500,
MIN_HOMEPAGE_CHARS=300).  This ensures these tests exercise the "good quality"
path without triggering the fallback.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.research import (
    CompanyProfile,
    PreprocessedContent,
    ResearchOutput,
    ResearchRequest,
    ScrapedPage,
)
from app.services.llm_client import LLMClientError
from app.services.research_agent import ResearchError, run_research


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_PROFILE = CompanyProfile(
    business_summary="Stripe is a financial infrastructure platform.",
    products_services=["payments", "billing", "fraud prevention"],
    target_audience=["developers", "startups", "enterprises"],
    brand_tone=["professional", "innovative", "technical"],
    usp="Developer-first financial infrastructure for the internet.",
    industry_category="Fintech",
)

FAKE_PAGE = ScrapedPage(url="https://stripe.com", title="Stripe", body_text="Payments for the internet.")

FAKE_PREPROCESSED = PreprocessedContent(
    company_name="Stripe",
    homepage_summary="Stripe powers payments for the internet. " * 20,  # >300 chars
    combined_context="Stripe is a financial platform...",
    word_count=600,  # above MIN_WORD_COUNT (500)
)


def _make_request() -> ResearchRequest:
    return ResearchRequest(company_name="Stripe", company_url="https://stripe.com")


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path_returns_valid_research_output():
    """All services succeed → valid ResearchOutput returned."""
    with (
        patch(
            "app.services.research_agent.scrape_company",
            new_callable=AsyncMock,
            return_value=[FAKE_PAGE],
        ),
        patch(
            "app.services.research_agent.preprocess",
            return_value=FAKE_PREPROCESSED,
        ),
        patch(
            "app.services.research_agent.analyze_company",
            new_callable=AsyncMock,
            return_value=FAKE_PROFILE,
        ),
        patch(
            "app.services.research_agent.save_debug_snapshot",
            return_value=Path("debug/research_outputs/stripe_test.json"),
        ),
        patch(
            "app.services.research_agent.scrape_company_headless",
            new_callable=AsyncMock,
        ) as headless_mock,
    ):
        result = await run_research(_make_request())

    assert isinstance(result, ResearchOutput)
    assert result.company_name == "Stripe"
    assert result.company_url == "https://stripe.com/"
    assert result.profile.business_summary == FAKE_PROFILE.business_summary
    assert result.metadata.pages_scraped == 1
    assert result.metadata.llm_model_used != ""
    assert result.metadata.processing_time_seconds >= 0
    # Good quality — headless should NOT be called
    headless_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Scraper raises exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scraper_exception_raises_research_error():
    """Scraper raises an exception → ResearchError propagated."""
    with patch(
        "app.services.research_agent.scrape_company",
        new_callable=AsyncMock,
        side_effect=ConnectionError("DNS resolution failed"),
    ):
        with pytest.raises(ConnectionError, match="DNS resolution failed"):
            await run_research(_make_request())


# ---------------------------------------------------------------------------
# 3. No pages scraped
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_pages_scraped_raises_research_error():
    """Both static and headless return empty → ResearchError raised."""
    with (
        patch(
            "app.services.research_agent.scrape_company",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.research_agent.scrape_company_headless",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        with pytest.raises(ResearchError, match="Both static and headless scraping failed"):
            await run_research(_make_request())


# ---------------------------------------------------------------------------
# 4. Gemini failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_failure_propagates():
    """Gemini analysis fails → LLMClientError surfaces."""
    with (
        patch(
            "app.services.research_agent.scrape_company",
            new_callable=AsyncMock,
            return_value=[FAKE_PAGE],
        ),
        patch(
            "app.services.research_agent.preprocess",
            return_value=FAKE_PREPROCESSED,
        ),
        patch(
            "app.services.research_agent.analyze_company",
            new_callable=AsyncMock,
            side_effect=LLMClientError("Gemini 503 Service Unavailable"),
        ),
        patch(
            "app.services.research_agent.scrape_company_headless",
            new_callable=AsyncMock,
        ),
    ):
        with pytest.raises(LLMClientError, match="Gemini 503"):
            await run_research(_make_request())


# ---------------------------------------------------------------------------
# 5. Debug persistence failure → research still succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_debug_persistence_failure_does_not_kill_research():
    """Debug snapshot save fails → research still returns valid output."""
    with (
        patch(
            "app.services.research_agent.scrape_company",
            new_callable=AsyncMock,
            return_value=[FAKE_PAGE],
        ),
        patch(
            "app.services.research_agent.preprocess",
            return_value=FAKE_PREPROCESSED,
        ),
        patch(
            "app.services.research_agent.analyze_company",
            new_callable=AsyncMock,
            return_value=FAKE_PROFILE,
        ),
        patch(
            "app.services.research_agent.save_debug_snapshot",
            side_effect=OSError("Disk full"),
        ),
        patch(
            "app.services.research_agent.scrape_company_headless",
            new_callable=AsyncMock,
        ),
    ):
        result = await run_research(_make_request())

    # Research must still succeed
    assert isinstance(result, ResearchOutput)
    assert result.company_name == "Stripe"
    assert result.profile.business_summary == FAKE_PROFILE.business_summary
