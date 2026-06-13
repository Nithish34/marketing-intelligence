import asyncio
import logging

from app.services.scraper import scrape_company

logging.basicConfig(level=logging.INFO)

async def main():
    print("Testing static fetch failure and headless fallback...")
    # Scrape a site known to block simple Python requests with 403
    # G2.com is a good example of this. We will just attempt to scrape the homepage.
    pages = await scrape_company("https://www.g2.com", max_pages=1)
    
    if pages:
        print(f"Success! Scraped {len(pages)} pages.")
        print(f"Homepage title: {pages[0].title}")
    else:
        print("Scrape failed.")

if __name__ == "__main__":
    asyncio.run(main())
