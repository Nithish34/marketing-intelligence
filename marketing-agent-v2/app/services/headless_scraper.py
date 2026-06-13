"""Headless browser scraper — Playwright-based fallback for JS-heavy sites.

Used ONLY as a fallback when static scraping produces low-quality results.
This is NOT the default scraping path.  Static httpx scraping is always
tried first, and only when extraction quality is poor (low word count,
thin homepage) does the orchestrator call this module.

Reuses parsing logic from ``scraper.py`` to maintain consistent output
format (``ScrapedPage``) and page-discovery heuristics.

Data flow::

    scrape_company_headless(url)
      ├─ launch headless Chromium
      ├─ _fetch_page_headless()  (homepage)   # navigate + wait for JS
      ├─ _parse_page()                        # reused from scraper.py
      ├─ _discover_target_pages()             # reused from scraper.py
      └─ loop: navigate + parse remaining target pages
"""

from __future__ import annotations

import asyncio
import logging

from app.schemas.research import ScrapedPage
from app.services.scraper import (
    MAX_PAGES,
    REQUEST_DELAY_SECONDS,
    _discover_target_pages,
    _get_domain,
    _parse_page,
    _truncate_large_html,
)


logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────

HEADLESS_TIMEOUT_MS: int = 30_000       # Page navigation timeout (ms)
HEADLESS_RENDER_WAIT_MS: int = 3_000    # Wait for JS rendering after load (ms)
HEADLESS_USER_AGENT: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ── Private helpers ────────────────────────────────────────────────────


async def _fetch_page_headless(page, url: str) -> tuple[str, str] | None:
    """Navigate to *url* in a Playwright page, wait for render.

    Returns ``(html, final_url)`` or ``None`` on failure.
    Never raises — logs and returns ``None``.
    """
    try:
        await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=HEADLESS_TIMEOUT_MS,
        )
        # Give JS frameworks time to render content
        await page.wait_for_timeout(HEADLESS_RENDER_WAIT_MS)

        html = await page.content()
        final_url = page.url
        html = _truncate_large_html(html)
        return html, final_url

    except Exception as exc:
        logger.warning("Headless navigation failed for %s: %s", url, exc)
        return None


# ── Public entry point ─────────────────────────────────────────────────


async def scrape_company_headless(
    url: str,
    max_pages: int | None = None,
) -> list[ScrapedPage]:
    """Scrape a company website using headless Chromium.

    Same contract as ``scrape_company()`` — returns ``list[ScrapedPage]``,
    never raises.  Returns an empty list on failure.

    Parameters
    ----------
    url:
        Company website URL (scheme optional — ``https://`` is assumed).
    max_pages:
        Cap on pages to scrape.  Defaults to ``settings.scrape_max_pages``.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.error(
            "playwright is not installed.  Install with: "
            "pip install playwright && playwright install chromium"
        )
        return []

    if max_pages is None:
        max_pages = MAX_PAGES

    # ── Normalise URL ────────────────────────────────────────────────
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    url = url.rstrip("/")

    base_domain = _get_domain(url)
    pages: list[ScrapedPage] = []
    visited: set[str] = set()

    logger.info("Starting headless scrape of %s (max %d pages)", url, max_pages)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                context = await browser.new_context(
                    user_agent=HEADLESS_USER_AGENT,
                )
                page = await context.new_page()

                # ── 1. Homepage ──────────────────────────────────────
                result = await _fetch_page_headless(page, url)
                if result is None:
                    logger.error(
                        "Headless: failed to fetch homepage %s", url,
                    )
                    return pages

                html, final_url = result
                visited.add(final_url)
                visited.add(url)

                homepage = _parse_page(html, final_url)
                pages.append(homepage)
                logger.info(
                    'Headless homepage scraped: "%s" (%d chars body)',
                    homepage.title,
                    len(homepage.body_text),
                )

                # Update domain if redirected
                redirected_domain = _get_domain(final_url)
                if redirected_domain != base_domain:
                    logger.info(
                        "Headless: domain changed after redirect: %s -> %s",
                        base_domain,
                        redirected_domain,
                    )
                    base_domain = redirected_domain

                # ── 2. Discover target pages ─────────────────────────
                target_urls = _discover_target_pages(
                    homepage.links, base_domain,
                )

                # ── 3. Scrape target pages ───────────────────────────
                for target_url in target_urls:
                    if len(pages) >= max_pages:
                        logger.info(
                            "Headless: reached max pages (%d)", max_pages,
                        )
                        break

                    if target_url in visited:
                        continue

                    # Polite delay between requests
                    await asyncio.sleep(REQUEST_DELAY_SECONDS)

                    result = await _fetch_page_headless(page, target_url)
                    if result is None:
                        continue

                    html, fetched_url = result
                    visited.add(fetched_url)
                    visited.add(target_url)

                    scraped_page = _parse_page(html, fetched_url)
                    pages.append(scraped_page)
                    logger.info(
                        'Headless page scraped: "%s" (%d chars body)',
                        scraped_page.title,
                        len(scraped_page.body_text),
                    )

            finally:
                await browser.close()

    except Exception as exc:
        logger.error("Headless scraping failed for %s: %r", url, exc)
        # Return whatever pages we managed to collect
        return pages

    logger.info(
        "Headless scrape complete: %d pages from %s",
        len(pages),
        base_domain,
    )
    return pages
