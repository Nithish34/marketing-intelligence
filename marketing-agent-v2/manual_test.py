import sys
import asyncio
import logging
from pathlib import Path

# Ensure the app folder is in path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Configure logging to see pipeline progress and fallback logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

from app.database import create_tables, close_db
from app.services.research_agent import run_research
from app.schemas.research import ResearchRequest
from app.config import settings

async def main():
    print("--- STARTING MANUAL TEST OF MARKETING AGENT V2 ---")
    print(f"App Name: {settings.app_name}")
    print(f"App Version: {settings.app_version}")
    print(f"Gemini Model: {settings.gemini_model}")
    print(f"Effective Database: {settings.effective_database_url}")
    
    # 1. Database table creation
    print("\n[1/2] Initializing database...")
    await create_tables()
    print("Database tables initialized successfully.")
    
    # 2. Run Research Agent
    company_name = "openai"
    company_url = "https://openai.com"
    print(f"\n[2/2] Running Research Agent for {company_name} ({company_url})...")
    
    try:
        request = ResearchRequest(company_name=company_name, company_url=company_url)
        result = await run_research(request)
        
        print("\n--- GEMINI EXTRACTION RESULT: CompanyProfile ---")
        profile = result.profile
        print(f"Business Summary: {profile.business_summary}")
        print(f"USP: {profile.usp}")
        print(f"Industry Category: {profile.industry_category}")
        print(f"Products & Services: {', '.join(profile.products_services)}")
        print(f"Target Audience: {', '.join(profile.target_audience)}")
        print(f"Brand Tone: {', '.join(profile.brand_tone)}")
        
        print("\n--- METADATA ---")
        print(f"Pages Scraped: {result.metadata.pages_scraped}")
        print(f"LLM Model Used: {result.metadata.llm_model_used}")
        print(f"Processing Time: {result.metadata.processing_time_seconds}s")
        print(f"Agent Version: {result.metadata.agent_version}")
    except Exception as e:
        print(f"\nResearch Agent failed: {e}")
        
    await close_db()
    print("\n--- MANUAL TEST COMPLETED ---")

if __name__ == "__main__":
    asyncio.run(main())
