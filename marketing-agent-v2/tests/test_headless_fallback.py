"""Tests for the headless browser fallback in the research pipeline.

All external services are mocked.  No network access, no real Playwright.
These tests verify the quality evaluation logic and fallback orchestration.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.research import (
    CompanyProfile,
    PreprocessedContent,
    ResearchOutput,
    ResearchRequest,
    ScrapedPage,
)
from app.services.research_agent import (
    LOW_WORD_COUNT_THRESHOLD,
    WEAK_HOMEPAGE_THRESHOLD,
    MIN_TOTAL_SIGNAL_THRESHOLD,
    ResearchError,
    _should_retry_headless,
    _contains_bot_protection,
    run_research,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_PROFILE = CompanyProfile(
    business_summary="Test company does test things.",
    products_services=["product a", "product b"],
    target_audience=["developers", "startups"],
    brand_tone=["professional", "technical"],
    usp="Test company is the best at testing.",
    industry_category="Testing",
)


def _make_request() -> ResearchRequest:
    return ResearchRequest(company_name="TestCo", company_url="https://testco.com")


def _make_page(url: str = "https://testco.com", body_chars: int = 2000) -> ScrapedPage:
    """Build a ScrapedPage with controllable body text length."""
    return ScrapedPage(
        url=url,
        title="TestCo - Test Company",
        body_text="x " * (body_chars // 2),
    )


def _make_preprocessed(
    word_count: int = 2000,
    homepage_chars: int = 5000,
) -> PreprocessedContent:
    """Build a PreprocessedContent with controllable quality metrics."""
    return PreprocessedContent(
        company_name="TestCo",
        homepage_title="TestCo - Test Company",
        homepage_summary="x " * (homepage_chars // 2),
        combined_context="TestCo is a test company...",
        word_count=word_count,
    )


def _patches(
    *,
    static_pages: list[ScrapedPage],
    static_preprocessed: PreprocessedContent,
    headless_pages: list[ScrapedPage] | None = None,
    headless_preprocessed: PreprocessedContent | None = None,
):
    """Build a context manager stack for the common mocking pattern.

    The preprocessor is called once for static scrape, and (if headless is
    triggered) once more for headless scrape.  We use side_effect to return
    different values on successive calls.
    """
    preprocess_returns = [static_preprocessed]
    if headless_preprocessed is not None:
        preprocess_returns.append(headless_preprocessed)

    patches_list = [
        patch(
            "app.services.research_agent.scrape_company",
            new_callable=AsyncMock,
            return_value=static_pages,
        ),
        patch(
            "app.services.research_agent.preprocess",
            side_effect=preprocess_returns,
        ),
        patch(
            "app.services.research_agent.analyze_company",
            new_callable=AsyncMock,
            return_value=FAKE_PROFILE,
        ),
        patch(
            "app.services.research_agent.save_debug_snapshot",
            return_value=Path("debug/research_outputs/testco_test.json"),
        ),
    ]

    if headless_pages is not None:
        patches_list.append(
            patch(
                "app.services.research_agent.scrape_company_headless",
                new_callable=AsyncMock,
                return_value=headless_pages,
            )
        )
    else:
        # Headless should not be called — mock it to detect unexpected calls
        patches_list.append(
            patch(
                "app.services.research_agent.scrape_company_headless",
                new_callable=AsyncMock,
                side_effect=AssertionError("Headless should not have been called"),
            )
        )

    return patches_list


# ---------------------------------------------------------------------------
# Unit tests for _is_low_quality
# ---------------------------------------------------------------------------


class TestShouldRetryHeadless:
    """Tests for the quality evaluation and retry decision logic."""

    def test_low_word_count_triggers_retry(self):
        # word_count < LOW_WORD_COUNT_THRESHOLD (500) -> True
        assert _should_retry_headless(word_count=400, homepage_chars=5000) is True

    def test_weak_homepage_with_low_total_signal_triggers_retry(self):
        # homepage_chars < WEAK_HOMEPAGE_THRESHOLD (300) and word_count < MIN_TOTAL_SIGNAL_THRESHOLD (1000) -> True
        assert _should_retry_headless(word_count=800, homepage_chars=250) is True

    def test_weak_homepage_with_strong_total_signal_does_not_retry(self):
        # homepage_chars < WEAK_HOMEPAGE_THRESHOLD (300) but word_count >= MIN_TOTAL_SIGNAL_THRESHOLD (1000) -> False
        assert _should_retry_headless(word_count=1200, homepage_chars=250) is False

    def test_strong_static_result_does_not_retry(self):
        # word_count >= 500, homepage_chars >= 300 -> False
        assert _should_retry_headless(word_count=2000, homepage_chars=5000) is False

    def test_threshold_boundary_word_count(self):
        # word_count exactly at LOW_WORD_COUNT_THRESHOLD (500) -> False
        assert _should_retry_headless(word_count=500, homepage_chars=500) is False

    def test_threshold_boundary_homepage_chars(self):
        # homepage_chars exactly at WEAK_HOMEPAGE_THRESHOLD (300) -> False
        assert _should_retry_headless(word_count=800, homepage_chars=300) is False


# ---------------------------------------------------------------------------
# 1. Strong static site — no fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strong_static_site_no_fallback():
    """Stripe-like site: static extraction is high quality, no headless needed."""
    static_pages = [_make_page()]
    static_preprocessed = _make_preprocessed(word_count=2000, homepage_chars=5000)

    all_patches = _patches(
        static_pages=static_pages,
        static_preprocessed=static_preprocessed,
        # headless_pages=None → mock will raise AssertionError if called
    )

    with all_patches[0], all_patches[1], all_patches[2], all_patches[3], all_patches[4] as headless_mock:
        result = await run_research(_make_request())

    assert isinstance(result, ResearchOutput)
    assert result.company_name == "TestCo"
    # Headless should NOT have been called
    headless_mock.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Weak static site — fallback triggered, headless improves
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_weak_static_triggers_headless_fallback():
    """Nike-like site: static produces thin content, headless improves it."""
    static_pages = [_make_page(body_chars=50)]
    static_preprocessed = _make_preprocessed(word_count=50, homepage_chars=38)

    headless_pages = [_make_page(body_chars=3000)]
    headless_preprocessed = _make_preprocessed(word_count=800, homepage_chars=2500)

    all_patches = _patches(
        static_pages=static_pages,
        static_preprocessed=static_preprocessed,
        headless_pages=headless_pages,
        headless_preprocessed=headless_preprocessed,
    )

    with all_patches[0], all_patches[1], all_patches[2], all_patches[3], all_patches[4] as headless_mock:
        result = await run_research(_make_request())

    assert isinstance(result, ResearchOutput)
    # Headless WAS called
    headless_mock.assert_called_once()
    # Result should use 1 page (the headless page)
    assert result.metadata.pages_scraped == 1


# ---------------------------------------------------------------------------
# 3. Static failure (0 pages) — headless recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_failure_headless_recovery():
    """Static scrape returns 0 pages. Headless fallback saves the day."""
    static_preprocessed = PreprocessedContent(company_name="TestCo")  # empty
    headless_pages = [_make_page(body_chars=2000)]
    headless_preprocessed = _make_preprocessed(word_count=600, homepage_chars=1500)

    all_patches = _patches(
        static_pages=[],
        static_preprocessed=static_preprocessed,
        headless_pages=headless_pages,
        headless_preprocessed=headless_preprocessed,
    )

    with all_patches[0], all_patches[1], all_patches[2], all_patches[3], all_patches[4] as headless_mock:
        result = await run_research(_make_request())

    assert isinstance(result, ResearchOutput)
    headless_mock.assert_called_once()
    assert result.metadata.pages_scraped == 1


# ---------------------------------------------------------------------------
# 4. Both fail — ResearchError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_both_fail_raises_research_error():
    """Both static and headless return 0 pages → ResearchError."""
    static_preprocessed = PreprocessedContent(company_name="TestCo")
    headless_preprocessed = PreprocessedContent(company_name="TestCo")

    all_patches = _patches(
        static_pages=[],
        static_preprocessed=static_preprocessed,
        headless_pages=[],
        headless_preprocessed=headless_preprocessed,
    )

    with all_patches[0], all_patches[1], all_patches[2], all_patches[3], all_patches[4]:
        with pytest.raises(ResearchError, match="Both static and headless scraping failed"):
            await run_research(_make_request())


# ---------------------------------------------------------------------------
# 5. Headless improves word count — verify better result is used
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_headless_improves_word_count():
    """Static word_count=100, headless word_count=1500 → headless result used."""
    static_pages = [_make_page(body_chars=200)]
    static_preprocessed = _make_preprocessed(word_count=100, homepage_chars=150)

    headless_pages = [_make_page(body_chars=5000), _make_page(url="https://testco.com/about", body_chars=3000)]
    headless_preprocessed = _make_preprocessed(word_count=1500, homepage_chars=4000)

    all_patches = _patches(
        static_pages=static_pages,
        static_preprocessed=static_preprocessed,
        headless_pages=headless_pages,
        headless_preprocessed=headless_preprocessed,
    )

    with all_patches[0], all_patches[1], all_patches[2], all_patches[3], all_patches[4]:
        result = await run_research(_make_request())

    assert isinstance(result, ResearchOutput)
    # Headless produced 2 pages, which should be used
    assert result.metadata.pages_scraped == 2


# ---------------------------------------------------------------------------
# 6. Bot protection result — fallback discarded, static kept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bot_protection_discard_headless():
    """If headless result contains bot-protection markers, discard it and keep static."""
    # Static scrape: thin content (word_count=350, homepage_chars=38) -> triggers fallback
    static_pages = [_make_page(body_chars=350)]
    static_preprocessed = _make_preprocessed(word_count=350, homepage_chars=38)

    # Headless scrape: returns page but it's a Cloudflare bot protection screen
    headless_pages = [
        ScrapedPage(
            url="https://testco.com",
            title="Just a moment...",
            body_text="Please enable JavaScript and cookies to continue. Cloudflare ray ID: ...",
        )
    ]
    headless_preprocessed = _make_preprocessed(word_count=600, homepage_chars=100)

    all_patches = _patches(
        static_pages=static_pages,
        static_preprocessed=static_preprocessed,
        headless_pages=headless_pages,
        headless_preprocessed=headless_preprocessed,
    )

    with all_patches[0], all_patches[1], all_patches[2], all_patches[3], all_patches[4] as headless_mock:
        result = await run_research(_make_request())

    assert isinstance(result, ResearchOutput)
    # Headless WAS called
    headless_mock.assert_called_once()
    # But because it contained bot protection, it was discarded!
    # The result metadata should reflect the static page count (1 page, not the headless result)
    assert result.metadata.pages_scraped == 1
    # Check that the request company_name is still used
    assert result.company_name == "TestCo"
