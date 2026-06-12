"""Manual end-to-end test of the Marketing Agent V2 research pipeline.

Uses run_research() to exercise the full orchestrated pipeline:
  ResearchRequest → scrape → preprocess → analyze → debug snapshot → ResearchOutput
"""

import sys
import asyncio
from pathlib import Path

# Ensure the app folder is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.config import settings
from app.schemas.research import ResearchRequest
from app.services.research_agent import run_research


async def main():
    print("--- STARTING MANUAL TEST OF MARKETING AGENT V2 ---")
    print(f"App Name: {settings.app_name}")
    print(f"App Version: {settings.app_version}")
    print(f"Gemini Model: {settings.gemini_model}")
    print()

    if not settings.gemini_api_key:
        print("ERROR: GEMINI_API_KEY is not set. Cannot run research.")
        return

    request = ResearchRequest(
        company_name="Stripe",
        company_url="https://stripe.com",
    )

    print(f"Running research for: {request.company_name} ({request.company_url})")
    print("Pipeline: scrape -> preprocess -> analyze -> snapshot -> result")
    print()

    try:
        result = await run_research(request)
    except Exception as e:
        print(f"Research failed: {type(e).__name__}: {e}")
        return

    # Display results
    profile = result.profile
    meta = result.metadata

    print("--- RESEARCH OUTPUT ---")
    print(f"Company:          {result.company_name}")
    print(f"URL:              {result.company_url}")
    print(f"Industry:         {profile.industry_category}")
    print(f"Business Summary: {profile.business_summary}")
    print(f"USP:              {profile.usp}")
    print(f"Products:         {', '.join(profile.products_services)}")
    print(f"Target Audience:  {', '.join(profile.target_audience)}")
    print(f"Brand Tone:       {', '.join(profile.brand_tone)}")
    print()
    print("--- METADATA ---")
    print(f"Agent Version:    {meta.agent_version}")
    print(f"Pages Scraped:    {meta.pages_scraped}")
    print(f"Model Used:       {meta.llm_model_used}")
    print(f"Processing Time:  {meta.processing_time_seconds}s")
    print(f"Timestamp:        {meta.research_timestamp}")
    print()
    print("--- MANUAL TEST COMPLETED ---")


if __name__ == "__main__":
    asyncio.run(main())
