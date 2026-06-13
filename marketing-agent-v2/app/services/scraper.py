"""Website scraper for company intelligence extraction.

Scrapes a company website to extract structured page data for downstream
preprocessing and LLM analysis.  Designed to be polite, fast-failing, and
resource-efficient on low-spec hardware (8 GB RAM, i3).

Architecture
------------
The public entry point is ``scrape_company(url)``.  Internally the module is
organised into five layers, each independent and testable:

1. **Text cleaning** — ``_clean_text()`` normalises whitespace everywhere.
2. **URL helpers**   — normalise, classify internal/external, extract domain.
3. **Robots.txt**    — async fetch + stdlib ``RobotFileParser``.
4. **HTTP fetch**    — single-page GET with size/type guards.
5. **HTML parsing**  — BS4 extraction split into *before* and *after*
   boilerplate removal so link discovery uses the full DOM while content
   extraction sees only meaningful text.

Data flow::

    scrape_company(url)
      ├─ _load_robots_txt()              # what are we allowed to fetch?
      ├─ _fetch_page_html()  (homepage)  # GET → (html, final_url)
      ├─ _parse_page()                   # BS4 → ScrapedPage
      │    ├─ _extract_title()           #   before strip
      │    ├─ _extract_meta_description()
      │    ├─ _extract_links()           #   before strip (nav links needed)
      │    ├─ _strip_boilerplate()       #   in-place removal of noise
      │    ├─ _extract_headings()        #   after strip
      │    └─ _extract_body_text()       #   after strip
      ├─ _discover_target_pages()        # keyword match on homepage links
      └─ loop: fetch + parse remaining target pages
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup, Tag

try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from app.config import settings
from app.schemas.research import ScrapedPage


# ── Logging ────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────

MAX_PAGES: int = settings.scrape_max_pages                  # 5
TIMEOUT_SECONDS: int = settings.scrape_timeout_seconds       # 30
REQUEST_DELAY_SECONDS: float = settings.scrape_delay_seconds # 1.0
MAX_PAGE_SIZE_BYTES: int = settings.scrape_max_page_size_kb * 1024  # 500 KB
USER_AGENT: str = settings.scrape_user_agent
MAX_CONTENT_CHARS: int = 50_000  # truncate body text beyond this


def _truncate_large_html(html: str) -> str:
    """Truncate HTML content if it exceeds the maximum page size limit."""
    if len(html) > MAX_PAGE_SIZE_BYTES:
        logger.warning("Page exceeded max size. Truncating.")
        return html[:MAX_PAGE_SIZE_BYTES]
    return html


# Keywords used to identify company-intelligence pages from homepage links.
# Each category maps to URL-path tokens that signal the page type.
# We pick at most ONE url per category → max 4 internal + 1 homepage = 5.
_PAGE_KEYWORDS: dict[str, list[str]] = {
    "about": [
        "about", "company", "who-we-are", "our-story",
        "team", "mission", "our-mission",
    ],
    "products": [
        "product", "service", "solution", "platform",
        "feature", "offering", "what-we-do", "capabilities",
    ],
    "pricing": ["pricing", "plan", "packages"],
    "contact": ["contact", "get-in-touch", "reach-us"],
}

# CSS class / id substrings that mark non-content elements.
_GARBAGE_PATTERNS: tuple[str, ...] = (
    "cookie", "consent", "banner", "popup", "modal", "gdpr",
    "newsletter", "subscribe", "sidebar", "advertisement",
    "ad-wrapper", "social-share", "share-button", "nav-menu",
    "breadcrumb", "announcement", "alert-bar", "notification",
    "chat-widget", "intercom", "drift", "hubspot-messages",
)


# ═══════════════════════════════════════════════════════════════════════
#  1. TEXT CLEANING
# ═══════════════════════════════════════════════════════════════════════

def _clean_text(text: str) -> str:
    """Normalise whitespace, strip zero-width chars, collapse blank lines."""
    if not text:
        return ""
    # Replace special whitespace and zero-width characters with a space
    text = re.sub(r"[\t\r\xa0\u200b\u200c\u200d\ufeff]+", " ", text)
    # Collapse runs of spaces (not newlines) into one
    text = re.sub(r" {2,}", " ", text)
    # Strip each line individually, drop empties
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
#  2. URL HELPERS
# ═══════════════════════════════════════════════════════════════════════

def _normalize_url(base_url: str, href: str) -> str:
    """Resolve *href* against *base_url*, strip fragment, deduplicate slash."""
    resolved = urljoin(base_url, href)
    parsed = urlparse(resolved)
    # Drop the fragment; keep everything else
    clean = parsed._replace(fragment="").geturl()
    # Remove trailing slash for dedup (except bare domain root "/")
    if clean.endswith("/") and parsed.path not in ("", "/"):
        clean = clean.rstrip("/")
    return clean


def _get_domain(url: str) -> str:
    """Extract the netloc in lowercase (e.g. ``'www.stripe.com'``)."""
    return urlparse(url).netloc.lower()


def _is_internal_url(url: str, base_domain: str) -> bool:
    """True when *url* belongs to *base_domain* or a subdomain of it."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", ""):
        return False
    domain = parsed.netloc.lower()
    # Strip optional "www." on both sides for more robust matching
    raw_base = base_domain.removeprefix("www.")
    raw_domain = domain.removeprefix("www.")
    return raw_domain == raw_base or raw_domain.endswith(f".{raw_base}")


# ═══════════════════════════════════════════════════════════════════════
#  3. ROBOTS.TXT
# ═══════════════════════════════════════════════════════════════════════

async def _load_robots_txt(
    client: httpx.AsyncClient,
    base_url: str,
) -> RobotFileParser:
    """Fetch and parse ``robots.txt``.  Allows everything on failure."""
    rp = RobotFileParser()
    robots_url = urljoin(base_url + "/", "/robots.txt")

    try:
        resp = await client.get(robots_url, timeout=10)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
            logger.info("Loaded robots.txt from %s", robots_url)
        else:
            logger.info(
                "No robots.txt at %s (HTTP %d) — allowing all",
                robots_url, resp.status_code,
            )
            rp.allow_all = True  # type: ignore[attr-defined]
    except Exception as exc:
        logger.warning(
            "Failed to fetch robots.txt from %s: %s — allowing all",
            robots_url, exc,
        )
        rp.allow_all = True  # type: ignore[attr-defined]

    return rp


def _is_allowed(rp: RobotFileParser, url: str, user_agent: str) -> bool:
    """Check robots.txt permission for *url*."""
    if getattr(rp, "allow_all", False):
        return True
    return rp.can_fetch(user_agent, url)


# ═══════════════════════════════════════════════════════════════════════
#  4. HTTP FETCHING
# ═══════════════════════════════════════════════════════════════════════

async def _fetch_page_html_headless(url: str) -> tuple[str, str] | None:
    """Fallback fetch using a headless browser via Playwright."""
    if not HAS_PLAYWRIGHT:
        logger.error("Playwright not installed. Cannot attempt headless fetch for %s", url)
        return None

    logger.info("Attempting headless fallback fetch for %s", url)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()
            
            response = await page.goto(url, timeout=TIMEOUT_SECONDS * 1000, wait_until="networkidle")
            
            if response is None:
                logger.warning("Headless fetch returned no response for %s", url)
                await browser.close()
                return None
                
            if response.status != 200:
                logger.warning("Headless fetch HTTP %d for %s", response.status, url)
                # Note: Not aborting here, sometimes 403/503 from Cloudflare renders the real page after challenge
            
            html = await page.content()
            final_url = page.url
            
            await browser.close()
            
            html = _truncate_large_html(html)
            logger.info("Headless fetch successful for %s (%d KB)", final_url, len(html.encode("utf-8")) // 1024)
            return html, final_url
            
    except PlaywrightTimeoutError:
        logger.warning("Headless fetch timeout for %s — skipping", url)
        return None
    except Exception as exc:
        logger.error("Headless fetch failed for %s: %r — skipping", url, exc)
        return None


async def _fetch_page_html(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[str, str] | None:
    """GET a page.  Returns ``(html_text, final_url)`` or ``None``.

    Guards against non-HTML responses, oversized pages, and all common
    HTTP/network errors.  Never raises — logs and returns ``None``.
    """
    try:
        resp = await client.get(url, follow_redirects=True, timeout=TIMEOUT_SECONDS)
        final_url = str(resp.url)

        if resp.status_code != 200:
            logger.warning("HTTP %d for %s — attempting headless fallback", resp.status_code, url)
            if HAS_PLAYWRIGHT:
                return await _fetch_page_html_headless(url)
            return None

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            logger.info("Non-HTML content at %s (%s) — skipping", url, content_type)
            return None

        html = _truncate_large_html(resp.text)
        logger.info("Fetched %s (%d KB)", final_url, len(html.encode("utf-8")) // 1024)
        return html, final_url

    except httpx.TimeoutException:
        logger.warning("Timeout fetching %s after %ds — attempting headless fallback", url, TIMEOUT_SECONDS)
        if HAS_PLAYWRIGHT:
            return await _fetch_page_html_headless(url)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning("HTTP error fetching %s: %s — attempting headless fallback", url, exc)
        if HAS_PLAYWRIGHT:
            return await _fetch_page_html_headless(url)
        return None
    except httpx.HTTPError as exc:
        logger.warning("Network error fetching %s: %s — attempting headless fallback", url, exc)
        if HAS_PLAYWRIGHT:
            return await _fetch_page_html_headless(url)
        return None
    except Exception as exc:
        logger.error("Unexpected error fetching %s: %r — skipping", url, exc)
        return None


# ═══════════════════════════════════════════════════════════════════════
#  5. HTML PARSING
# ═══════════════════════════════════════════════════════════════════════

# ── Extraction helpers (called BEFORE boilerplate strip) ─────────────

def _extract_title(soup: BeautifulSoup) -> str:
    """Page ``<title>`` text, falling back to the first ``<h1>``."""
    tag = soup.find("title")
    if tag and tag.string:
        return _clean_text(tag.string)
    h1 = soup.find("h1")
    if h1:
        return _clean_text(h1.get_text())
    return ""


def _extract_meta_description(soup: BeautifulSoup) -> str:
    """``<meta name="description">`` content, with ``og:description`` fallback."""
    tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if tag and tag.get("content"):
        return _clean_text(str(tag["content"]))
    og = soup.find("meta", attrs={"property": "og:description"})
    if og and og.get("content"):
        return _clean_text(str(og["content"]))
    return ""


def _extract_links(soup: BeautifulSoup, page_url: str) -> list[str]:
    """All ``<a href>`` links, resolved to absolute URLs and deduplicated."""
    links: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        # Skip non-navigable hrefs
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        normalised = _normalize_url(page_url, href)
        if normalised not in seen:
            seen.add(normalised)
            links.append(normalised)
    return links


# ── Boilerplate removal (in-place) ───────────────────────────────────

def _has_garbage_marker(element: Tag) -> bool:
    """True if the element's class or id matches any garbage pattern."""
    classes = " ".join(element.get("class", [])).lower()
    el_id = (element.get("id") or "").lower()
    combined = f"{classes} {el_id}"
    return any(p in combined for p in _GARBAGE_PATTERNS)


def _strip_boilerplate(soup: BeautifulSoup) -> None:
    """Remove non-content elements in place.

    Order matters:
    1. Invisible tags  (script, style, …)
    2. Garbage-marked elements (cookie banners, chat widgets, …)
    3. Structural noise  (nav, footer)

    We snapshot targets into a list before decomposing to avoid
    mutating the tree while iterating (decomposing a parent orphans
    its children, setting their ``.attrs`` to ``None``).
    """
    # 1. Always-invisible tags
    for tag in list(soup.find_all(
        ["script", "style", "noscript", "iframe", "svg", "link"]
    )):
        tag.decompose()

    # 2. Elements with garbage class/id — snapshot first, then decompose
    targets = [
        el for el in soup.find_all(True)
        if isinstance(el, Tag) and el.attrs is not None and _has_garbage_marker(el)
    ]
    for element in targets:
        if element.parent is not None:   # still in the tree
            element.decompose()

    # 3. Structural navigation / footer (links already extracted)
    for tag in list(soup.find_all(["nav", "footer"])):
        if tag.parent is not None:
            tag.decompose()


# ── Content extraction helpers (called AFTER boilerplate strip) ──────

def _extract_headings(soup: BeautifulSoup) -> list[str]:
    """H1–H3 heading text, cleaned and deduplicated."""
    headings: list[str] = []
    seen: set[str] = set()
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = _clean_text(tag.get_text())
        key = text.lower()
        if text and len(text) > 2 and key not in seen:
            seen.add(key)
            headings.append(text)
    return headings


def _extract_body_text(soup: BeautifulSoup) -> str:
    """Clean paragraph/body text from the main content area.

    Strategy:
    1. Find the semantic content root (``<main>``, ``<article>``,
       ``role="main"``, or ``<body>``).
    2. Collect text from paragraph-level elements (``<p>``, ``<li>``, …).
    3. If that yields too little, fall back to ``get_text()`` on the root.
    4. Truncate to ``MAX_CONTENT_CHARS``.
    """
    content_root = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.find("body")
        or soup
    )

    # Prefer text from semantic paragraph-level elements
    content_tags = content_root.find_all(
        ["p", "li", "blockquote", "td", "dd", "figcaption"]
    )
    fragments: list[str] = []
    for tag in content_tags:
        text = _clean_text(tag.get_text())
        if text and len(text) >= 15:          # skip trivial fragments
            fragments.append(text)

    if fragments:
        result = "\n".join(fragments)
    else:
        # Fallback: raw text from the content root
        raw = content_root.get_text(separator="\n", strip=True)
        result = _clean_text(raw)

    # Guard against massive pages
    if len(result) > MAX_CONTENT_CHARS:
        result = result[:MAX_CONTENT_CHARS] + "\n[…truncated]"

    return result


# ── Full page parser ─────────────────────────────────────────────────

def _parse_page(html: str, url: str) -> ScrapedPage:
    """Parse raw HTML into a ``ScrapedPage``.

    Extraction order matters:
    - title, meta, links → extracted from the **full** DOM
    - headings, body_text → extracted **after** boilerplate is stripped
    """
    soup = BeautifulSoup(html, "lxml")

    # --- Before stripping (full DOM) ---
    title = _extract_title(soup)
    meta_desc = _extract_meta_description(soup)
    links = _extract_links(soup, url)

    # --- Strip, then extract content ---
    _strip_boilerplate(soup)
    headings = _extract_headings(soup)
    body_text = _extract_body_text(soup)

    return ScrapedPage(
        url=url,
        title=title,
        meta_description=meta_desc,
        headings=headings,
        body_text=body_text,
        links=links,
        scrape_timestamp=datetime.now(timezone.utc),
    )


# ═══════════════════════════════════════════════════════════════════════
#  6. INTERNAL PAGE DISCOVERY
# ═══════════════════════════════════════════════════════════════════════

def _discover_target_pages(
    links: list[str],
    base_domain: str,
) -> list[str]:
    """Pick internal pages most likely to contain company intelligence.

    Scans all *links* for URL-path matches against ``_PAGE_KEYWORDS``.
    Returns at most one URL per category, ordered by category priority.
    """
    internal = [lnk for lnk in links if _is_internal_url(lnk, base_domain)]

    discovered: dict[str, str] = {}       # category → best URL

    for link in internal:
        path = urlparse(link).path.lower().strip("/")
        if not path:
            continue

        # Skip deep paths (unlikely to be top-level company pages)
        if path.count("/") > 2:
            continue
        # Skip static files
        if re.search(
            r"\.(pdf|jpg|jpeg|png|gif|svg|webp|ico|css|js|zip|xml|json|woff2?)$",
            path,
        ):
            continue

        for category, keywords in _PAGE_KEYWORDS.items():
            if category in discovered:
                continue  # already found a page for this category

            # Split path on common separators
            segments = re.split(r"[/\-_.]", path)

            # Exact segment match is preferred
            if any(kw in segments for kw in keywords):
                discovered[category] = link
                break

            # Substring match as fallback (e.g. "/about-us" → "about" in path)
            if any(kw in path for kw in keywords):
                discovered[category] = link
                break

    urls = list(discovered.values())
    if urls:
        logger.info(
            "Discovered %d target pages: %s",
            len(urls),
            {cat: urlparse(u).path for cat, u in discovered.items()},
        )
    else:
        logger.info("No additional target pages discovered from %d links", len(internal))

    return urls


# ═══════════════════════════════════════════════════════════════════════
#  7. PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

async def scrape_company(
    url: str,
    max_pages: int | None = None,
) -> list[ScrapedPage]:
    """Scrape a company website and return structured page data.

    Parameters
    ----------
    url:
        Company website URL (scheme optional — ``https://`` is assumed).
    max_pages:
        Cap on pages to scrape.  Defaults to ``settings.scrape_max_pages``.

    Returns
    -------
    list[ScrapedPage]
        Successfully scraped pages.  Always returns a list (never raises).
        May be empty if the homepage itself is unreachable.

    Flow
    ----
    1. Normalise URL and resolve domain.
    2. Check ``robots.txt``.
    3. Fetch and parse the homepage.
    4. Discover internal target pages (about, products, pricing, contact).
    5. Fetch and parse each target page with a polite delay.
    6. Return all pages.
    """
    if max_pages is None:
        max_pages = MAX_PAGES

    # ── Normalise URL ────────────────────────────────────────────────
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    url = url.rstrip("/")

    base_domain = _get_domain(url)
    pages: list[ScrapedPage] = []
    visited: set[str] = set()

    logger.info("Starting scrape of %s (max %d pages)", url, max_pages)

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        timeout=TIMEOUT_SECONDS,
    ) as client:

        # ── 1. Robots.txt ────────────────────────────────────────────
        robots = await _load_robots_txt(client, url)

        # ── 2. Homepage ──────────────────────────────────────────────
        if not _is_allowed(robots, url, USER_AGENT):
            logger.warning("robots.txt disallows homepage %s — aborting", url)
            return pages

        result = await _fetch_page_html(client, url)
        if result is None:
            logger.error("Failed to fetch homepage %s — aborting", url)
            return pages

        html, final_url = result
        visited.add(final_url)
        visited.add(url)       # also mark the pre-redirect URL

        homepage = _parse_page(html, final_url)
        pages.append(homepage)
        logger.info(
            "Homepage scraped: \"%s\" (%d links, %d headings, %d chars body)",
            homepage.title,
            len(homepage.links),
            len(homepage.headings),
            len(homepage.body_text),
        )

        # If the domain changed after redirect, update for link matching
        redirected_domain = _get_domain(final_url)
        if redirected_domain != base_domain:
            logger.info(
                "Domain changed after redirect: %s → %s",
                base_domain, redirected_domain,
            )
            base_domain = redirected_domain

        # ── 3. Discover internal pages ───────────────────────────────
        target_urls = _discover_target_pages(homepage.links, base_domain)

        # ── 4. Scrape target pages ───────────────────────────────────
        for target_url in target_urls:
            if len(pages) >= max_pages:
                logger.info("Reached max pages limit (%d) — stopping", max_pages)
                break

            if target_url in visited:
                continue

            if not _is_allowed(robots, target_url, USER_AGENT):
                logger.info("robots.txt disallows %s — skipping", target_url)
                continue

            # Polite delay between requests
            await asyncio.sleep(REQUEST_DELAY_SECONDS)

            result = await _fetch_page_html(client, target_url)
            if result is None:
                continue

            html, fetched_url = result
            visited.add(fetched_url)
            visited.add(target_url)

            page = _parse_page(html, fetched_url)
            pages.append(page)
            logger.info(
                "Page scraped: \"%s\" (%d chars body)",
                page.title, len(page.body_text),
            )

    logger.info(
        "Scrape complete: %d pages from %s", len(pages), base_domain,
    )
    return pages
