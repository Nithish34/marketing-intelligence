"""Content preprocessor — converts raw scraped pages into LLM-ready context.

This module sits between the scraper (deterministic HTML extraction) and the
future LLM reasoning layer.  It performs four jobs:

1. **Cleaning**       — strip low-signal junk (CTA spam, cookie text, legal boilerplate).
2. **Deduplication**  — marketing sites repeat content heavily; keep only one copy.
3. **Organisation**   — classify pages by type and route their content into named sections.
4. **Context building** — merge all sections into a single, structured, LLM-optimised prompt block.

The preprocessor does NOT do intelligence.  It does signal extraction + noise
reduction so the LLM sees high-signal business context, not raw website junk.

Data flow::

    list[ScrapedPage]
         │
    ┌────┴────────────────────────┐
    │  for each page:             │
    │    _classify_page()         │  → tag as homepage/about/products/pricing/contact/other
    │    _clean_paragraphs()      │  → split body → filter junk → deduplicate
    │    _classify_links()        │  → split into internal vs external
    │    deduplicate headings     │
    └────┬────────────────────────┘
         │
    _build_combined_context()      → assemble sections into LLM-ready text
         │
    PreprocessedContent
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from app.schemas.research import PreprocessedContent, ScrapedPage


# ── Logging ────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  CONSTANTS & HEURISTICS
# ═══════════════════════════════════════════════════════════════════════

# Paragraphs shorter than this are likely button labels / CTA fragments
MIN_USEFUL_TEXT_LENGTH: int = 25

# Phrases that are almost never useful business context.
# Matched against normalised (lowercase, stripped) text.
LOW_SIGNAL_PHRASES: tuple[str, ...] = (
    # Cookie / privacy
    "accept cookies",
    "accept all cookies",
    "cookie policy",
    "cookie settings",
    "cookie preferences",
    "manage cookies",
    "privacy policy",
    "terms of service",
    "terms and conditions",
    "terms of use",
    "all rights reserved",
    # CTA spam
    "book a demo",
    "book demo",
    "request a demo",
    "request demo",
    "schedule a demo",
    "get a demo",
    "get started",
    "get started free",
    "get started for free",
    "start free trial",
    "start your free trial",
    "try for free",
    "try it free",
    "sign up free",
    "sign up for free",
    "create free account",
    "create account",
    "start now",
    "start today",
    # Auth
    "log in",
    "login",
    "sign in",
    "sign up",
    "sign out",
    "register",
    "forgot password",
    "reset password",
    # Generic nav / footer
    "contact sales",
    "contact us",
    "talk to sales",
    "talk to an expert",
    "chat with us",
    "follow us",
    "careers",
    "we're hiring",
    "press room",
    "newsroom",
    "sitemap",
    "accessibility",
    # Social
    "share on twitter",
    "share on facebook",
    "share on linkedin",
    "follow us on",
)

# URL path segments used to classify pages by type.
_PAGE_TYPE_PATTERNS: dict[str, list[str]] = {
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


# ═══════════════════════════════════════════════════════════════════════
#  1. TEXT NORMALISATION
# ═══════════════════════════════════════════════════════════════════════

def _normalize_for_comparison(text: str) -> str:
    """Lowercase, collapse whitespace, strip — used only for dedup/matching."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _clean_whitespace(text: str) -> str:
    """Collapse runs of whitespace while preserving paragraph breaks."""
    text = re.sub(r"[\t\r\xa0\u200b\u200c\u200d\ufeff]+", " ", text)
    text = re.sub(r" {2,}", " ", text)
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
#  2. JUNK DETECTION
# ═══════════════════════════════════════════════════════════════════════

def _is_low_signal(text: str, min_length: int = MIN_USEFUL_TEXT_LENGTH) -> bool:
    """True if *text* matches a known low-signal / junk pattern.

    Args:
        text: The text to evaluate.
        min_length: Minimum character count.  Paragraphs use 25;
                    headings should pass a smaller value (e.g. 3).

    Checks:
    1. Text is too short to be meaningful content.
    2. Exact match against LOW_SIGNAL_PHRASES (after normalisation).
    3. Starts with a low-signal phrase.
    4. Text looks like a copyright line ("© 2024 Acme Corp").
    """
    normalised = _normalize_for_comparison(text)

    if not normalised:
        return True

    # Too short to carry business meaning
    if len(normalised) < min_length:
        return True

    # Exact phrase match
    if normalised in LOW_SIGNAL_PHRASES:
        return True

    # Starts with a low-signal phrase (e.g. "sign up for our newsletter today")
    if any(normalised.startswith(phrase) for phrase in LOW_SIGNAL_PHRASES):
        return True

    # Copyright lines
    if re.match(r"^[©®™\d\s\-,]+$", normalised):
        return True
    if normalised.startswith("©") or normalised.startswith("copyright"):
        return True
    if "all rights reserved" in normalised:
        return True

    return False


# ═══════════════════════════════════════════════════════════════════════
#  3. PARAGRAPH CLEANING & DEDUPLICATION
# ═══════════════════════════════════════════════════════════════════════

def _clean_paragraphs(body_text: str, seen: set[str]) -> list[str]:
    """Split body text into paragraphs, remove junk, deduplicate.

    Args:
        body_text: Raw body text from a ScrapedPage.
        seen: Mutable set of normalised paragraphs already encountered
              (shared across pages for cross-page dedup).

    Returns:
        List of clean, unique paragraphs from this page.
    """
    paragraphs = body_text.split("\n")
    clean: list[str] = []

    for para in paragraphs:
        para = _clean_whitespace(para)
        if not para:
            continue

        # Junk detection
        if _is_low_signal(para):
            continue

        # Cross-page deduplication
        key = _normalize_for_comparison(para)
        if key in seen:
            continue
        seen.add(key)

        clean.append(para)

    return clean


# ═══════════════════════════════════════════════════════════════════════
#  4. HEADING DEDUPLICATION & VALUE PROP EXTRACTION
# ═══════════════════════════════════════════════════════════════════════

def _deduplicate_headings(
    pages: list[ScrapedPage],
) -> tuple[list[str], list[str]]:
    """Merge and deduplicate headings across all pages.

    Returns:
        (all_headings, key_value_propositions)
        - all_headings: every unique heading across all pages.
        - key_value_propositions: headings that look like hero statements
          or strong value props (longer, descriptive phrases).
    """
    seen: set[str] = set()
    all_headings: list[str] = []
    value_props: list[str] = []

    for page in pages:
        for heading in page.headings:
            heading = _clean_whitespace(heading)
            if not heading:
                continue
            key = _normalize_for_comparison(heading)
            if key in seen:
                continue
            if _is_low_signal(heading, min_length=3):
                continue
            seen.add(key)
            all_headings.append(heading)

            # Value prop heuristic: longer headings that feel like
            # positioning statements, not just section labels.
            # "Financial infrastructure for the internet" → value prop
            # "Products" → section label
            if len(heading) >= 30 and not heading.endswith("?"):
                value_props.append(heading)

    return all_headings, value_props


# ═══════════════════════════════════════════════════════════════════════
#  5. PAGE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════

def _classify_page(page: ScrapedPage, is_first: bool) -> str:
    """Classify a page as homepage/about/products/pricing/contact/other.

    Args:
        page: The scraped page.
        is_first: True if this is the first page (assumed to be homepage).

    Returns:
        One of: "homepage", "about", "products", "pricing", "contact", "other".
    """
    if is_first:
        return "homepage"

    path = urlparse(page.url).path.lower().strip("/")
    if not path:
        return "homepage"

    # Split path on separators and check against patterns
    segments = re.split(r"[/\-_.]", path)

    for page_type, keywords in _PAGE_TYPE_PATTERNS.items():
        # Exact segment match
        if any(kw in segments for kw in keywords):
            return page_type
        # Substring match (e.g. "about-us")
        if any(kw in path for kw in keywords):
            return page_type

    # Fallback: check the page title
    title_lower = page.title.lower()
    for page_type, keywords in _PAGE_TYPE_PATTERNS.items():
        if any(kw in title_lower for kw in keywords):
            return page_type

    return "other"


# ═══════════════════════════════════════════════════════════════════════
#  6. LINK CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════

def _classify_links(
    pages: list[ScrapedPage],
    base_domain: str,
) -> tuple[list[str], list[str]]:
    """Split all links across pages into internal and external, deduplicated.

    Returns:
        (internal_titles, external_links)
        - internal_titles: titles of internal pages found in links.
        - external_links: unique external URLs (potential competitors/partners).
    """
    # Collect internal page titles from scraped pages themselves
    internal_titles: list[str] = []
    seen_titles: set[str] = set()
    for page in pages:
        if page.title and page.title.lower() not in seen_titles:
            seen_titles.add(page.title.lower())
            internal_titles.append(page.title)

    # Collect external links (deduplicated)
    external: list[str] = []
    seen_external: set[str] = set()

    raw_base = base_domain.removeprefix("www.")

    for page in pages:
        for link in page.links:
            parsed = urlparse(link)
            if parsed.scheme not in ("http", "https"):
                continue
            domain = parsed.netloc.lower().removeprefix("www.")

            # Skip internal links
            if domain == raw_base or domain.endswith(f".{raw_base}"):
                continue

            # Skip common non-competitor external links
            if _is_generic_external(domain):
                continue

            if link not in seen_external:
                seen_external.add(link)
                external.append(link)

    return internal_titles, external


def _is_generic_external(domain: str) -> bool:
    """True if the domain is a generic service, not a potential competitor."""
    generic_domains = (
        "google.com", "facebook.com", "twitter.com", "x.com",
        "linkedin.com", "instagram.com", "youtube.com", "tiktok.com",
        "github.com", "medium.com", "wordpress.com", "wp.com",
        "apple.com", "play.google.com", "apps.apple.com",
        "cloudflare.com", "amazonaws.com", "googleapis.com",
        "cdn.jsdelivr.net", "unpkg.com", "fonts.googleapis.com",
        "gravatar.com", "schema.org", "w3.org",
    )
    return any(
        domain == g or domain.endswith(f".{g}")
        for g in generic_domains
    )


# ═══════════════════════════════════════════════════════════════════════
#  7. COMBINED CONTEXT BUILDER
# ═══════════════════════════════════════════════════════════════════════

def _build_combined_context(
    company_name: str,
    homepage_title: str,
    meta_description: str,
    homepage_summary: str,
    about_section: str,
    products_section: str,
    pricing_section: str,
    contact_section: str,
    key_value_propositions: list[str],
    all_headings: list[str],
) -> str:
    """Assemble all sections into a single structured context block.

    The output is formatted as labelled sections so the LLM can quickly
    parse the information.  Empty sections are omitted to keep it compact.
    """
    parts: list[str] = []

    parts.append(f"=== COMPANY: {company_name} ===")

    if homepage_title:
        parts.append(f"Title: {homepage_title}")
    if meta_description:
        parts.append(f"Description: {meta_description}")

    if key_value_propositions:
        parts.append("")
        parts.append("--- KEY VALUE PROPOSITIONS ---")
        for vp in key_value_propositions:
            parts.append(f"• {vp}")

    if homepage_summary:
        parts.append("")
        parts.append("--- HOMEPAGE ---")
        parts.append(homepage_summary)

    if about_section:
        parts.append("")
        parts.append("--- ABOUT / COMPANY ---")
        parts.append(about_section)

    if products_section:
        parts.append("")
        parts.append("--- PRODUCTS / SERVICES ---")
        parts.append(products_section)

    if pricing_section:
        parts.append("")
        parts.append("--- PRICING ---")
        parts.append(pricing_section)

    if contact_section:
        parts.append("")
        parts.append("--- CONTACT ---")
        parts.append(contact_section)

    if all_headings:
        parts.append("")
        parts.append("--- ALL PAGE HEADINGS ---")
        for h in all_headings[:30]:  # cap to avoid noise
            parts.append(f"• {h}")

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
#  8. PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════

def preprocess(
    pages: list[ScrapedPage],
    company_name: str,
) -> PreprocessedContent:
    """Convert raw scraped pages into structured, LLM-ready content.

    This is the sole public entry point.  The function is synchronous,
    CPU-only, and runs in <100ms even on an i3 for typical inputs (≤5 pages).

    Args:
        pages: Output from ``scrape_company()``.  May be empty.
        company_name: The company being researched.

    Returns:
        A ``PreprocessedContent`` with all fields populated.
    """
    if not pages:
        logger.warning("No pages to preprocess for %s", company_name)
        return PreprocessedContent(company_name=company_name)

    logger.info(
        "Preprocessing %d pages for %s", len(pages), company_name,
    )

    # ── Determine base domain from homepage ──────────────────────────
    homepage_url = pages[0].url
    base_domain = urlparse(homepage_url).netloc.lower()

    # ── Pass 1: classify pages and clean content ─────────────────────
    seen_paragraphs: set[str] = set()    # cross-page dedup
    sections: dict[str, list[str]] = {
        "homepage": [],
        "about": [],
        "products": [],
        "pricing": [],
        "contact": [],
        "other": [],
    }

    for i, page in enumerate(pages):
        page_type = _classify_page(page, is_first=(i == 0))
        clean = _clean_paragraphs(page.body_text, seen_paragraphs)
        sections[page_type].extend(clean)
        logger.debug(
            "Page %d [%s] → %d clean paragraphs",
            i, page_type, len(clean),
        )

    # ── Pass 2: headings ─────────────────────────────────────────────
    all_headings, value_props = _deduplicate_headings(pages)

    # ── Pass 3: links ────────────────────────────────────────────────
    internal_titles, external_links = _classify_links(pages, base_domain)

    # ── Assemble sections ────────────────────────────────────────────
    homepage_summary = "\n".join(sections["homepage"])
    about_section = "\n".join(sections["about"])
    products_section = "\n".join(sections["products"])
    pricing_section = "\n".join(sections["pricing"])
    contact_section = "\n".join(sections["contact"])

    # Body text combined = all sections merged (for backward compat + word count)
    all_sections = [
        homepage_summary, about_section, products_section,
        pricing_section, contact_section,
        "\n".join(sections["other"]),
    ]
    body_text_combined = "\n\n".join(s for s in all_sections if s)

    # ── Homepage metadata ────────────────────────────────────────────
    homepage = pages[0]
    homepage_title = homepage.title
    meta_description = homepage.meta_description

    # ── Combined context ─────────────────────────────────────────────
    combined_context = _build_combined_context(
        company_name=company_name,
        homepage_title=homepage_title,
        meta_description=meta_description,
        homepage_summary=homepage_summary,
        about_section=about_section,
        products_section=products_section,
        pricing_section=pricing_section,
        contact_section=contact_section,
        key_value_propositions=value_props,
        all_headings=all_headings,
    )

    word_count = len(body_text_combined.split())

    result = PreprocessedContent(
        company_name=company_name,
        homepage_title=homepage_title,
        meta_description=meta_description,
        homepage_summary=homepage_summary,
        about_section=about_section,
        products_section=products_section,
        pricing_section=pricing_section,
        contact_section=contact_section,
        all_headings=all_headings,
        key_value_propositions=value_props,
        body_text_combined=body_text_combined,
        internal_page_titles=internal_titles,
        external_links=external_links,
        combined_context=combined_context,
        word_count=word_count,
    )

    logger.info(
        "Preprocessing complete for %s: %d headings, %d words, "
        "%d external links, %d value props",
        company_name,
        len(all_headings),
        word_count,
        len(external_links),
        len(value_props),
    )

    return result
