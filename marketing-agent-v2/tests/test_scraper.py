"""Tests for the website scraper.

Two test groups:
    1. Unit tests — pure functions, no network, fast.
    2. Integration tests — hit real websites, require network.

Run everything:
    .venv\\Scripts\\python.exe -m pytest "marketing agent v2/tests/test_scraper.py" -v

Run only unit tests (fast):
    .venv\\Scripts\\python.exe -m pytest "marketing agent v2/tests/test_scraper.py" -v -k "not integration"

Run only integration tests:
    .venv\\Scripts\\python.exe -m pytest "marketing agent v2/tests/test_scraper.py" -v -k "integration"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Ensure the v2 app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.scraper import (
    _clean_text,
    _normalize_url,
    _get_domain,
    _is_internal_url,
    _has_garbage_marker,
    _strip_boilerplate,
    _extract_title,
    _extract_meta_description,
    _extract_headings,
    _extract_links,
    _extract_body_text,
    _parse_page,
    _discover_target_pages,
    scrape_company,
    _truncate_large_html,
    MAX_PAGE_SIZE_BYTES,
)
from app.schemas.research import ScrapedPage
from bs4 import BeautifulSoup, Tag


# ═══════════════════════════════════════════════════════════════════════
#  UNIT TESTS — no network, fast
# ═══════════════════════════════════════════════════════════════════════


class TestCleanText:
    """Tests for _clean_text()."""

    def test_collapses_spaces(self):
        assert _clean_text("hello    world") == "hello world"

    def test_strips_lines(self):
        assert _clean_text("  hello  \n  world  ") == "hello\nworld"

    def test_removes_empty_lines(self):
        assert _clean_text("hello\n\n\n\nworld") == "hello\nworld"

    def test_handles_tabs_and_special_whitespace(self):
        assert _clean_text("hello\t\r\xa0world") == "hello world"

    def test_removes_zero_width_chars(self):
        assert _clean_text("hello\u200bworld") == "hello world"

    def test_empty_string(self):
        assert _clean_text("") == ""

    def test_none_safe(self):
        assert _clean_text("") == ""


class TestNormalizeUrl:
    """Tests for _normalize_url()."""

    def test_resolves_relative_path(self):
        result = _normalize_url("https://example.com/page", "/about")
        assert result == "https://example.com/about"

    def test_resolves_relative_no_slash(self):
        result = _normalize_url("https://example.com/page/", "about")
        assert result == "https://example.com/page/about"

    def test_strips_fragment(self):
        result = _normalize_url("https://example.com", "/about#team")
        assert result == "https://example.com/about"

    def test_removes_trailing_slash(self):
        result = _normalize_url("https://example.com", "/about/")
        assert result == "https://example.com/about"

    def test_keeps_root_slash(self):
        result = _normalize_url("https://example.com", "/")
        assert result == "https://example.com/"

    def test_absolute_url_passthrough(self):
        result = _normalize_url("https://example.com", "https://other.com/page")
        assert result == "https://other.com/page"


class TestGetDomain:
    """Tests for _get_domain()."""

    def test_basic(self):
        assert _get_domain("https://www.stripe.com/products") == "www.stripe.com"

    def test_no_www(self):
        assert _get_domain("https://stripe.com") == "stripe.com"

    def test_with_port(self):
        assert _get_domain("http://localhost:8000/api") == "localhost:8000"

    def test_uppercase_normalised(self):
        assert _get_domain("https://WWW.Example.COM") == "www.example.com"


class TestIsInternalUrl:
    """Tests for _is_internal_url()."""

    def test_same_domain(self):
        assert _is_internal_url("https://stripe.com/about", "stripe.com") is True

    def test_www_subdomain(self):
        assert _is_internal_url("https://www.stripe.com/about", "stripe.com") is True

    def test_base_has_www(self):
        assert _is_internal_url("https://stripe.com/about", "www.stripe.com") is True

    def test_other_subdomain(self):
        assert _is_internal_url("https://docs.stripe.com/api", "stripe.com") is True

    def test_external_domain(self):
        assert _is_internal_url("https://google.com", "stripe.com") is False

    def test_non_http_scheme(self):
        assert _is_internal_url("ftp://stripe.com/file", "stripe.com") is False

    def test_mailto_scheme(self):
        assert _is_internal_url("mailto:hi@stripe.com", "stripe.com") is False


class TestHasGarbageMarker:
    """Tests for _has_garbage_marker()."""

    def test_cookie_class(self):
        soup = BeautifulSoup('<div class="cookie-banner">text</div>', "lxml")
        tag = soup.find("div")
        assert _has_garbage_marker(tag) is True

    def test_consent_id(self):
        soup = BeautifulSoup('<div id="gdpr-consent">text</div>', "lxml")
        tag = soup.find("div")
        assert _has_garbage_marker(tag) is True

    def test_clean_element(self):
        soup = BeautifulSoup('<div class="main-content">text</div>', "lxml")
        tag = soup.find("div")
        assert _has_garbage_marker(tag) is False

    def test_newsletter_class(self):
        soup = BeautifulSoup('<section class="newsletter-signup">text</section>', "lxml")
        tag = soup.find("section")
        assert _has_garbage_marker(tag) is True


class TestExtractTitle:
    """Tests for _extract_title()."""

    def test_from_title_tag(self):
        soup = BeautifulSoup("<html><head><title>My Company</title></head></html>", "lxml")
        assert _extract_title(soup) == "My Company"

    def test_fallback_to_h1(self):
        soup = BeautifulSoup("<html><body><h1>Welcome</h1></body></html>", "lxml")
        assert _extract_title(soup) == "Welcome"

    def test_empty_when_missing(self):
        soup = BeautifulSoup("<html><body><p>No title</p></body></html>", "lxml")
        assert _extract_title(soup) == ""


class TestExtractMetaDescription:
    """Tests for _extract_meta_description()."""

    def test_standard_meta(self):
        html = '<html><head><meta name="description" content="We build things."></head></html>'
        soup = BeautifulSoup(html, "lxml")
        assert _extract_meta_description(soup) == "We build things."

    def test_og_fallback(self):
        html = '<html><head><meta property="og:description" content="OG desc."></head></html>'
        soup = BeautifulSoup(html, "lxml")
        assert _extract_meta_description(soup) == "OG desc."

    def test_empty_when_missing(self):
        soup = BeautifulSoup("<html><head></head></html>", "lxml")
        assert _extract_meta_description(soup) == ""


class TestExtractHeadings:
    """Tests for _extract_headings()."""

    def test_extracts_h1_h2_h3(self):
        html = "<h1>Title</h1><h2>Section</h2><h3>Sub</h3><h4>Ignored</h4>"
        soup = BeautifulSoup(html, "lxml")
        result = _extract_headings(soup)
        assert result == ["Title", "Section", "Sub"]

    def test_deduplicates(self):
        html = "<h1>Title</h1><h2>Title</h2>"
        soup = BeautifulSoup(html, "lxml")
        result = _extract_headings(soup)
        assert result == ["Title"]

    def test_skips_tiny_headings(self):
        html = "<h1>OK heading</h1><h2>Hi</h2>"  # "Hi" is only 2 chars
        soup = BeautifulSoup(html, "lxml")
        result = _extract_headings(soup)
        assert result == ["OK heading"]


class TestExtractLinks:
    """Tests for _extract_links()."""

    def test_resolves_relative(self):
        html = '<a href="/about">About</a><a href="/products">Products</a>'
        soup = BeautifulSoup(html, "lxml")
        links = _extract_links(soup, "https://example.com")
        assert "https://example.com/about" in links
        assert "https://example.com/products" in links

    def test_deduplicates(self):
        html = '<a href="/about">A</a><a href="/about">B</a>'
        soup = BeautifulSoup(html, "lxml")
        links = _extract_links(soup, "https://example.com")
        assert links.count("https://example.com/about") == 1

    def test_skips_javascript_and_mailto(self):
        html = '<a href="javascript:void(0)">X</a><a href="mailto:a@b.com">Y</a>'
        soup = BeautifulSoup(html, "lxml")
        links = _extract_links(soup, "https://example.com")
        assert links == []


class TestExtractBodyText:
    """Tests for _extract_body_text()."""

    def test_extracts_paragraphs(self):
        html = "<main><p>This is a valid paragraph with enough text.</p></main>"
        soup = BeautifulSoup(html, "lxml")
        result = _extract_body_text(soup)
        assert "This is a valid paragraph" in result

    def test_skips_short_fragments(self):
        html = "<main><p>OK</p><p>This paragraph has enough text to pass.</p></main>"
        soup = BeautifulSoup(html, "lxml")
        result = _extract_body_text(soup)
        assert "OK" not in result
        assert "This paragraph" in result

    def test_fallback_to_get_text(self):
        html = "<body><div>Only div content, no paragraphs, but enough text to extract.</div></body>"
        soup = BeautifulSoup(html, "lxml")
        result = _extract_body_text(soup)
        assert "div content" in result


class TestStripBoilerplate:
    """Tests for _strip_boilerplate()."""

    def test_removes_script_and_style(self):
        html = "<body><script>var x=1;</script><style>body{}</style><p>Real content.</p></body>"
        soup = BeautifulSoup(html, "lxml")
        _strip_boilerplate(soup)
        assert soup.find("script") is None
        assert soup.find("style") is None
        assert "Real content" in soup.get_text()

    def test_removes_cookie_banner(self):
        html = '<body><div class="cookie-banner">Accept cookies</div><p>Content.</p></body>'
        soup = BeautifulSoup(html, "lxml")
        _strip_boilerplate(soup)
        assert "cookie" not in soup.get_text().lower()
        assert "Content" in soup.get_text()

    def test_removes_nav_and_footer(self):
        html = "<body><nav>Menu</nav><main><p>Article.</p></main><footer>Footer</footer></body>"
        soup = BeautifulSoup(html, "lxml")
        _strip_boilerplate(soup)
        assert soup.find("nav") is None
        assert soup.find("footer") is None
        assert "Article" in soup.get_text()


class TestParsePage:
    """Tests for _parse_page() — full HTML to ScrapedPage."""

    def test_full_parse(self):
        html = """
        <html>
        <head>
            <title>Acme Corp</title>
            <meta name="description" content="We make widgets.">
        </head>
        <body>
            <nav><a href="/about">About</a><a href="/products">Products</a></nav>
            <main>
                <h1>Welcome to Acme</h1>
                <h2>Our Mission</h2>
                <p>Acme Corp builds the best widgets in the world for developers and teams.</p>
                <p>Founded in 2020, we serve thousands of customers globally with reliable tooling.</p>
            </main>
            <footer><a href="https://twitter.com/acme">Twitter</a></footer>
            <script>alert('x')</script>
        </body>
        </html>
        """
        page = _parse_page(html, "https://acme.com")

        assert page.url == "https://acme.com"
        assert page.title == "Acme Corp"
        assert page.meta_description == "We make widgets."
        assert "Welcome to Acme" in page.headings
        assert "Our Mission" in page.headings
        assert any("widgets" in t for t in [page.body_text])
        # Links should include nav + footer links (extracted before strip)
        assert "https://acme.com/about" in page.links
        assert "https://acme.com/products" in page.links
        assert "https://twitter.com/acme" in page.links
        # Script should not appear in body text
        assert "alert" not in page.body_text


class TestDiscoverTargetPages:
    """Tests for _discover_target_pages()."""

    def test_finds_about_and_products(self):
        links = [
            "https://example.com/about",
            "https://example.com/products",
            "https://example.com/blog",
            "https://example.com/careers",
        ]
        result = _discover_target_pages(links, "example.com")
        assert "https://example.com/about" in result
        assert "https://example.com/products" in result
        assert "https://example.com/blog" not in result

    def test_finds_pricing_and_contact(self):
        links = [
            "https://example.com/pricing",
            "https://example.com/contact",
        ]
        result = _discover_target_pages(links, "example.com")
        assert "https://example.com/pricing" in result
        assert "https://example.com/contact" in result

    def test_skips_external_links(self):
        links = [
            "https://other.com/about",
            "https://example.com/about",
        ]
        result = _discover_target_pages(links, "example.com")
        assert "https://other.com/about" not in result
        assert "https://example.com/about" in result

    def test_skips_deep_paths(self):
        links = [
            "https://example.com/blog/2024/01/about-our-journey",
        ]
        result = _discover_target_pages(links, "example.com")
        assert result == []

    def test_skips_static_files(self):
        links = [
            "https://example.com/about.pdf",
            "https://example.com/logo.png",
        ]
        result = _discover_target_pages(links, "example.com")
        assert result == []

    def test_handles_hyphenated_paths(self):
        links = [
            "https://example.com/about-us",
            "https://example.com/our-products",
        ]
        result = _discover_target_pages(links, "example.com")
        assert "https://example.com/about-us" in result

    def test_empty_links(self):
        result = _discover_target_pages([], "example.com")
        assert result == []


# ═══════════════════════════════════════════════════════════════════════
#  INTEGRATION TESTS — require network, hit real websites
# ═══════════════════════════════════════════════════════════════════════


def _run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


def _assert_valid_page(page: ScrapedPage, label: str) -> None:
    """Common assertions for any scraped page."""
    assert page.url, f"[{label}] URL should not be empty"
    assert page.title, f"[{label}] Title should not be empty"
    assert len(page.body_text) > 50, (
        f"[{label}] Body text too short ({len(page.body_text)} chars)"
    )
    assert page.scrape_timestamp is not None, f"[{label}] Timestamp missing"


class TestTruncateLargeHtml:
    """Tests for _truncate_large_html()."""

    def test_no_truncation_under_limit(self):
        content = "<html>hello</html>"
        assert _truncate_large_html(content) == content

    def test_truncation_over_limit(self):
        content = "a" * (MAX_PAGE_SIZE_BYTES + 100)
        truncated = _truncate_large_html(content)
        assert len(truncated) == MAX_PAGE_SIZE_BYTES
        assert truncated == "a" * MAX_PAGE_SIZE_BYTES


@pytest.mark.integration
class TestScrapeStripe:
    """Integration: scrape stripe.com."""

    def test_scrape_stripe(self):
        pages = _run(scrape_company("https://stripe.com", max_pages=3))

        assert len(pages) >= 1, "Should scrape at least the homepage"

        homepage = pages[0]
        _assert_valid_page(homepage, "Stripe homepage")

        # Stripe's title should mention Stripe
        assert "stripe" in homepage.title.lower(), f"Unexpected title: {homepage.title}"

        # Should find some links
        assert len(homepage.links) > 10, "Stripe homepage should have many links"

        # Should have headings
        assert len(homepage.headings) >= 1, "Should find at least one heading"

        print(f"\n--- Stripe: {len(pages)} pages scraped ---")
        for p in pages:
            print(f"  [{p.title}] {p.url} ({len(p.body_text)} chars)")


@pytest.mark.integration
class TestScrapeNotion:
    """Integration: scrape notion.so."""

    def test_scrape_notion(self):
        pages = _run(scrape_company("https://www.notion.com", max_pages=3))

        assert len(pages) >= 1, "Should scrape at least the homepage"

        homepage = pages[0]
        _assert_valid_page(homepage, "Notion homepage")

        print(f"\n--- Notion: {len(pages)} pages scraped ---")
        for p in pages:
            print(f"  [{p.title}] {p.url} ({len(p.body_text)} chars)")


@pytest.mark.integration
class TestScrapeHubSpot:
    """Integration: scrape hubspot.com."""

    def test_scrape_hubspot(self):
        pages = _run(scrape_company("https://www.hubspot.com", max_pages=3))

        assert len(pages) >= 1, "Should scrape at least the homepage"

        homepage = pages[0]
        _assert_valid_page(homepage, "HubSpot homepage")

        print(f"\n--- HubSpot: {len(pages)} pages scraped ---")
        for p in pages:
            print(f"  [{p.title}] {p.url} ({len(p.body_text)} chars)")


@pytest.mark.integration
class TestScrapeBasecamp:
    """Integration: scrape basecamp.com (smaller company)."""

    def test_scrape_basecamp(self):
        pages = _run(scrape_company("https://basecamp.com", max_pages=3))

        assert len(pages) >= 1, "Should scrape at least the homepage"

        homepage = pages[0]
        _assert_valid_page(homepage, "Basecamp homepage")

        print(f"\n--- Basecamp: {len(pages)} pages scraped ---")
        for p in pages:
            print(f"  [{p.title}] {p.url} ({len(p.body_text)} chars)")


@pytest.mark.integration
class TestScrapeEdgeCases:
    """Integration: error handling with bad inputs."""

    def test_invalid_domain(self):
        pages = _run(scrape_company("https://this-domain-absolutely-does-not-exist-12345.com"))
        assert pages == [], "Invalid domain should return empty list, not raise"

    def test_max_pages_respected(self):
        pages = _run(scrape_company("https://stripe.com", max_pages=1))
        assert len(pages) <= 1, "Should respect max_pages=1"

    def test_url_without_scheme(self):
        pages = _run(scrape_company("stripe.com", max_pages=1))
        assert len(pages) >= 1, "Should auto-add https:// scheme"
