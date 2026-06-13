"""Regression benchmarks for the Research Agent.

These tests hit real websites (Stripe, OpenAI, Nike, Vercel, Linear) to verify
that changes in scraper/preprocessor don't break extraction quality.
The Gemini API client is mocked to avoid rate limits and cost.
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.research import (
    CompanyProfile,
    ResearchOutput,
    ResearchRequest,
    ScrapedPage,
)
from app.services.research_agent import run_research

logger = logging.getLogger(__name__)

# FAKE CompanyProfile return for mocks
FAKE_BENCHMARK_PROFILE = CompanyProfile(
    business_summary="Mock summary for benchmark testing.",
    products_services=["Product A", "Product B"],
    target_audience=["Developers", "Enterprises"],
    brand_tone=["Innovative", "Technical"],
    usp="Mock USP for benchmark testing.",
    industry_category="Benchmark Testing",
)


@pytest.mark.benchmark
@pytest.mark.asyncio
class TestResearchBenchmarks:
    """Benchmark suite validating research pipeline logic and scraping thresholds."""

    @pytest.fixture(autouse=True)
    def mock_gemini_client(self):
        """Mock analyze_company to completely bypass Gemini API calls."""
        with patch("app.services.research_agent.analyze_company", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = FAKE_BENCHMARK_PROFILE
            yield mock_analyze

    def _verify_output_structure(self, result: ResearchOutput) -> None:
        """Helper to run standard sanity checks on the extraction structure and metadata."""
        assert isinstance(result, ResearchOutput)
        assert result.metadata.pages_scraped > 0
        assert result.metadata.processing_time_seconds >= 0
        assert result.metadata.llm_model_used
        assert result.metadata.agent_version
        
        # Verify LLM results populated (structural validation only)
        assert result.profile.business_summary
        assert result.profile.usp
        assert result.profile.industry_category
        assert len(result.profile.products_services) > 0
        assert len(result.profile.target_audience) > 0
        assert len(result.profile.brand_tone) > 0

    async def test_stripe_benchmark(self, mock_gemini_client):
        """Stripe: baseline SaaS. Expected high quality static scrape with >1000 words."""
        print("\n[Benchmark] Running Stripe benchmark...")
        request = ResearchRequest(company_name="Stripe", company_url="https://stripe.com")
        
        # Verify no unnecessary headless retry is called for a strong static site
        with patch("app.services.research_agent.scrape_company_headless", new_callable=AsyncMock) as mock_headless:
            result = await run_research(request)
            mock_headless.assert_not_called()
            
        self._verify_output_structure(result)
        
        # Inspect mock arguments to check preprocessed word count
        preprocessed = mock_gemini_client.call_args[0][0]
        print(f"[Benchmark] Stripe word count: {preprocessed.word_count}")
        assert preprocessed.word_count > 1000
        print("[Benchmark] Stripe Success")

    async def test_openai_benchmark(self, mock_gemini_client):
        """OpenAI: weak homepage but strong total signal. Expected NO headless retry and >1500 words."""
        print("\n[Benchmark] Running OpenAI benchmark...")
        request = ResearchRequest(company_name="OpenAI", company_url="https://openai.com")
        
        # Verify no unnecessary headless retry is called for OpenAI
        with patch("app.services.research_agent.scrape_company_headless", new_callable=AsyncMock) as mock_headless:
            result = await run_research(request)
            mock_headless.assert_not_called()
            
        self._verify_output_structure(result)
        
        # Inspect mock arguments to check preprocessed word count
        preprocessed = mock_gemini_client.call_args[0][0]
        print(f"[Benchmark] OpenAI word count: {preprocessed.word_count}")
        assert preprocessed.word_count > 1500
        print("[Benchmark] OpenAI Success")

    async def test_nike_benchmark(self, mock_gemini_client):
        """Nike: consumer brand. Expected retry behavior checks to handle weak/thin static content."""
        print("\n[Benchmark] Running Nike benchmark...")
        request = ResearchRequest(company_name="Nike", company_url="https://nike.com")
        
        result = await run_research(request)
        self._verify_output_structure(result)
        
        preprocessed = mock_gemini_client.call_args[0][0]
        print(f"[Benchmark] Nike word count: {preprocessed.word_count}")
        assert preprocessed.word_count > 200
        print("[Benchmark] Nike Success")

    async def test_vercel_benchmark(self, mock_gemini_client):
        """Vercel: modern JS-heavy site. Expected to handle frontend-heavy website structure."""
        print("\n[Benchmark] Running Vercel benchmark...")
        request = ResearchRequest(company_name="Vercel", company_url="https://vercel.com")
        
        result = await run_research(request)
        self._verify_output_structure(result)
        
        preprocessed = mock_gemini_client.call_args[0][0]
        print(f"[Benchmark] Vercel word count: {preprocessed.word_count}")
        assert preprocessed.word_count > 300
        print("[Benchmark] Vercel Success")

    async def test_linear_benchmark(self, mock_gemini_client):
        """Linear: large modern SaaS. Expected large-page handling to prevent skips and get >800 words."""
        print("\n[Benchmark] Running Linear benchmark...")
        request = ResearchRequest(company_name="Linear", company_url="https://linear.app")
        
        result = await run_research(request)
        self._verify_output_structure(result)
        
        preprocessed = mock_gemini_client.call_args[0][0]
        print(f"[Benchmark] Linear word count: {preprocessed.word_count}")
        assert preprocessed.word_count > 800
        print("[Benchmark] Linear Success")

    async def test_bot_protection_resilience(self, mock_gemini_client):
        """Bot protection resilience test: ensure block patterns do not crash the pipeline."""
        print("\n[Benchmark] Running Bot Protection Resilience benchmark...")
        request = ResearchRequest(company_name="BlockedCo", company_url="https://blockedco.com")
        
        # 1. Mock static scrape to return a thin page (triggers fallback retry)
        static_pages = [
            ScrapedPage(
                url="https://blockedco.com",
                title="BlockedCo Home",
                body_text="This is a longer body text that represents the company's business model and products and has enough characters to pass the preprocessor filter.",
            )
        ]
        
        # 2. Mock headless fallback scrape to return Cloudflare bot protection html
        headless_pages = [
            ScrapedPage(
                url="https://blockedco.com",
                title="Just a moment...",
                body_text="Verify you are human. Cloudflare ray ID: ...",
            )
        ]
        
        with patch("app.services.research_agent.scrape_company", new_callable=AsyncMock, return_value=static_pages), \
             patch("app.services.research_agent.scrape_company_headless", new_callable=AsyncMock, return_value=headless_pages):
            
            result = await run_research(request)
            
        assert isinstance(result, ResearchOutput)
        # Verify it discarded headless and kept static result (pages_scraped == 1)
        assert result.metadata.pages_scraped == 1
        
        # Verify preprocessed content is static
        preprocessed = mock_gemini_client.call_args[0][0]
        assert "business model and products" in preprocessed.combined_context
        print("[Benchmark] Bot Protection Resilience Success")
