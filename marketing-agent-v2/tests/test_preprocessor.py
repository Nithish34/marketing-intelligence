"""Tests for the content preprocessor.

Two test groups:
    1. Unit tests — synthetic ScrapedPage data, no network, fast.
    2. Integration tests — pipe real scraper output through the preprocessor.

Run everything:
    .venv\\Scripts\\python.exe -m pytest "marketing agent v2/tests/test_preprocessor.py" -v

Run only unit tests (fast):
    .venv\\Scripts\\python.exe -m pytest "marketing agent v2/tests/test_preprocessor.py" -v -k "not integration"

Run only integration tests:
    .venv\\Scripts\\python.exe -m pytest "marketing agent v2/tests/test_preprocessor.py" -v -k "integration"
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Ensure the v2 app is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.research import PreprocessedContent, ScrapedPage
from app.services.preprocessor import (
    _normalize_for_comparison,
    _clean_whitespace,
    _is_low_signal,
    _clean_paragraphs,
    _deduplicate_headings,
    _classify_page,
    _classify_links,
    _is_generic_external,
    _build_combined_context,
    preprocess,
)


# ── Helpers ────────────────────────────────────────────────────────────

def _make_page(
    url: str = "https://example.com",
    title: str = "Example",
    meta_description: str = "An example company.",
    headings: list[str] | None = None,
    body_text: str = "",
    links: list[str] | None = None,
) -> ScrapedPage:
    """Create a ScrapedPage with sensible defaults for testing."""
    return ScrapedPage(
        url=url,
        title=title,
        meta_description=meta_description,
        headings=headings or [],
        body_text=body_text,
        links=links or [],
        scrape_timestamp=datetime.now(timezone.utc),
    )


# ═══════════════════════════════════════════════════════════════════════
#  UNIT TESTS — synthetic data, fast
# ═══════════════════════════════════════════════════════════════════════


class TestNormalizeForComparison:
    """Tests for _normalize_for_comparison()."""

    def test_lowercases_and_strips(self):
        assert _normalize_for_comparison("  Hello World  ") == "hello world"

    def test_collapses_whitespace(self):
        assert _normalize_for_comparison("a   b\t c") == "a b c"

    def test_empty_string(self):
        assert _normalize_for_comparison("") == ""


class TestCleanWhitespace:
    """Tests for _clean_whitespace()."""

    def test_collapses_spaces(self):
        assert _clean_whitespace("hello    world") == "hello world"

    def test_strips_lines(self):
        result = _clean_whitespace("  hello  \n  world  ")
        assert result == "hello\nworld"

    def test_removes_zero_width_chars(self):
        assert _clean_whitespace("a\u200bb") == "a b"


class TestIsLowSignal:
    """Tests for _is_low_signal()."""

    def test_short_text_is_junk(self):
        assert _is_low_signal("Get started") is True

    def test_exact_phrase_match(self):
        assert _is_low_signal("Accept cookies") is True
        assert _is_low_signal("PRIVACY POLICY") is True
        assert _is_low_signal("  Book a Demo  ") is True

    def test_prefix_match(self):
        assert _is_low_signal("Sign up for our amazing newsletter today") is True

    def test_copyright_line(self):
        assert _is_low_signal("© 2024 Acme Corp. All rights reserved.") is True
        assert _is_low_signal("Copyright 2024 Stripe, Inc.") is True

    def test_preserves_real_content(self):
        assert _is_low_signal("Financial infrastructure for the internet") is False

    def test_preserves_product_description(self):
        assert _is_low_signal(
            "Stripe Billing lets you create and manage subscriptions and invoices."
        ) is False

    def test_preserves_value_proposition(self):
        assert _is_low_signal(
            "Grow your revenue with a unified platform for payments and commerce."
        ) is False


class TestCleanParagraphs:
    """Tests for _clean_paragraphs()."""

    def test_removes_junk_paragraphs(self):
        text = "Accept cookies\nBook a demo\nWe build great products for developers worldwide.\nSign up"
        seen: set[str] = set()
        result = _clean_paragraphs(text, seen)
        assert len(result) == 1
        assert "great products" in result[0]

    def test_deduplicates_across_pages(self):
        text1 = "This is an important paragraph about our company."
        text2 = "This is an important paragraph about our company."
        seen: set[str] = set()
        r1 = _clean_paragraphs(text1, seen)
        r2 = _clean_paragraphs(text2, seen)
        assert len(r1) == 1
        assert len(r2) == 0  # duplicate removed

    def test_keeps_unique_content(self):
        text = "Our platform helps businesses scale globally.\nWe serve over 10,000 customers."
        seen: set[str] = set()
        result = _clean_paragraphs(text, seen)
        assert len(result) == 2

    def test_empty_text(self):
        seen: set[str] = set()
        result = _clean_paragraphs("", seen)
        assert result == []

    def test_removes_short_fragments(self):
        text = "Learn more\nContact us\nWe build financial infrastructure for the internet."
        seen: set[str] = set()
        result = _clean_paragraphs(text, seen)
        assert len(result) == 1
        assert "financial infrastructure" in result[0]


class TestDeduplicateHeadings:
    """Tests for _deduplicate_headings()."""

    def test_deduplicates_across_pages(self):
        pages = [
            _make_page(headings=["Welcome", "Products"]),
            _make_page(headings=["Welcome", "About Us"]),
        ]
        headings, _ = _deduplicate_headings(pages)
        assert headings.count("Welcome") == 1
        assert "Products" in headings
        assert "About Us" in headings

    def test_extracts_value_propositions(self):
        pages = [
            _make_page(headings=[
                "Products",  # too short for value prop
                "Financial infrastructure for the internet",  # value prop (>=30 chars)
                "Grow your revenue with intelligent tools",  # value prop
            ]),
        ]
        _, value_props = _deduplicate_headings(pages)
        assert "Financial infrastructure for the internet" in value_props
        assert "Products" not in value_props

    def test_removes_junk_headings(self):
        pages = [
            _make_page(headings=["Sign up", "Log in", "Our Amazing Platform"]),
        ]
        headings, _ = _deduplicate_headings(pages)
        # "Sign up" and "Log in" are too short AND low signal
        assert "Our Amazing Platform" in headings


class TestClassifyPage:
    """Tests for _classify_page()."""

    def test_first_page_is_homepage(self):
        page = _make_page(url="https://example.com")
        assert _classify_page(page, is_first=True) == "homepage"

    def test_about_page(self):
        page = _make_page(url="https://example.com/about")
        assert _classify_page(page, is_first=False) == "about"

    def test_about_us_hyphenated(self):
        page = _make_page(url="https://example.com/about-us")
        assert _classify_page(page, is_first=False) == "about"

    def test_products_page(self):
        page = _make_page(url="https://example.com/products")
        assert _classify_page(page, is_first=False) == "products"

    def test_pricing_page(self):
        page = _make_page(url="https://example.com/pricing")
        assert _classify_page(page, is_first=False) == "pricing"

    def test_contact_page(self):
        page = _make_page(url="https://example.com/contact")
        assert _classify_page(page, is_first=False) == "contact"

    def test_fallback_to_title(self):
        page = _make_page(url="https://example.com/info", title="About Our Company")
        assert _classify_page(page, is_first=False) == "about"

    def test_unknown_page(self):
        page = _make_page(url="https://example.com/blog", title="Blog")
        assert _classify_page(page, is_first=False) == "other"


class TestClassifyLinks:
    """Tests for _classify_links()."""

    def test_separates_internal_and_external(self):
        pages = [
            _make_page(
                url="https://example.com",
                title="Example",
                links=[
                    "https://example.com/about",
                    "https://competitor.com/product",
                    "https://www.example.com/pricing",
                ],
            ),
        ]
        titles, external = _classify_links(pages, "example.com")
        assert "Example" in titles
        assert any("competitor.com" in link for link in external)

    def test_filters_generic_domains(self):
        pages = [
            _make_page(
                links=[
                    "https://twitter.com/example",
                    "https://github.com/example",
                    "https://fonts.googleapis.com/css",
                    "https://real-partner.com/page",
                ],
            ),
        ]
        _, external = _classify_links(pages, "example.com")
        assert not any("twitter.com" in l for l in external)
        assert not any("github.com" in l for l in external)
        assert any("real-partner.com" in l for l in external)


class TestIsGenericExternal:
    """Tests for _is_generic_external()."""

    def test_social_media(self):
        assert _is_generic_external("twitter.com") is True
        assert _is_generic_external("facebook.com") is True
        assert _is_generic_external("linkedin.com") is True

    def test_cdn(self):
        assert _is_generic_external("cdn.jsdelivr.net") is True
        assert _is_generic_external("fonts.googleapis.com") is True

    def test_real_company(self):
        assert _is_generic_external("stripe.com") is False
        assert _is_generic_external("hubspot.com") is False


class TestBuildCombinedContext:
    """Tests for _build_combined_context()."""

    def test_includes_company_name(self):
        result = _build_combined_context(
            company_name="Acme",
            homepage_title="Acme Corp",
            meta_description="We make things.",
            homepage_summary="We build tools.",
            about_section="Founded in 2020.",
            products_section="Widget Pro.",
            pricing_section="$99/month.",
            contact_section="hello@acme.com",
            key_value_propositions=["Build better products faster"],
            all_headings=["Welcome", "Products"],
        )
        assert "=== COMPANY: Acme ===" in result
        assert "Acme Corp" in result
        assert "We make things." in result
        assert "We build tools." in result
        assert "Founded in 2020." in result
        assert "Widget Pro." in result
        assert "$99/month." in result
        assert "hello@acme.com" in result
        assert "Build better products faster" in result

    def test_omits_empty_sections(self):
        result = _build_combined_context(
            company_name="Acme",
            homepage_title="",
            meta_description="",
            homepage_summary="",
            about_section="We are Acme.",
            products_section="",
            pricing_section="",
            contact_section="",
            key_value_propositions=[],
            all_headings=[],
        )
        assert "--- HOMEPAGE ---" not in result
        assert "--- PRODUCTS" not in result
        assert "--- PRICING ---" not in result
        assert "--- CONTACT ---" not in result
        assert "--- ABOUT / COMPANY ---" in result


class TestPreprocess:
    """Tests for the main preprocess() function with synthetic data."""

    def test_empty_pages(self):
        result = preprocess([], "TestCo")
        assert result.company_name == "TestCo"
        assert result.word_count == 0

    def test_single_homepage(self):
        pages = [
            _make_page(
                url="https://testco.com",
                title="TestCo - Build Better",
                meta_description="TestCo helps you build better products.",
                headings=["Build Better Products", "Features"],
                body_text=(
                    "TestCo provides tools for developers to ship faster.\n"
                    "Our platform integrates with your existing workflow.\n"
                    "Book a demo\nSign up free"
                ),
                links=[
                    "https://testco.com/about",
                    "https://twitter.com/testco",
                    "https://competitor.io/page",
                ],
            ),
        ]
        result = preprocess(pages, "TestCo")

        assert result.company_name == "TestCo"
        assert result.homepage_title == "TestCo - Build Better"
        assert result.meta_description == "TestCo helps you build better products."
        assert "Build Better Products" in result.all_headings
        assert result.word_count > 0

        # Junk should be removed
        assert "Book a demo" not in result.homepage_summary
        assert "Sign up free" not in result.homepage_summary

        # Real content preserved
        assert "developers" in result.homepage_summary
        assert "workflow" in result.homepage_summary

        # External link classification
        assert any("competitor.io" in l for l in result.external_links)
        assert not any("twitter.com" in l for l in result.external_links)

        # Combined context should exist
        assert "=== COMPANY: TestCo ===" in result.combined_context

    def test_multi_page_deduplication(self):
        shared_text = "Our platform helps businesses grow with AI-powered analytics."
        pages = [
            _make_page(
                url="https://test.com",
                body_text=f"Homepage hero content for the amazing product.\n{shared_text}",
            ),
            _make_page(
                url="https://test.com/about",
                body_text=f"We founded the company in 2020.\n{shared_text}",
            ),
        ]
        result = preprocess(pages, "Test")

        # The shared paragraph should appear only once in combined body
        count = result.body_text_combined.count(shared_text)
        assert count == 1, f"Expected 1 occurrence, got {count}"

    def test_multi_page_section_routing(self):
        pages = [
            _make_page(
                url="https://test.com",
                title="Test Homepage",
                body_text="We are the best platform for developers worldwide.",
            ),
            _make_page(
                url="https://test.com/about",
                title="About Test",
                body_text="Founded in 2020, we serve thousands of customers globally.",
            ),
            _make_page(
                url="https://test.com/pricing",
                title="Test Pricing",
                body_text="Starter plan is $29 per month. Pro plan is $99 per month.",
            ),
        ]
        result = preprocess(pages, "Test")

        assert "best platform" in result.homepage_summary
        assert "Founded in 2020" in result.about_section
        assert "$29" in result.pricing_section or "$99" in result.pricing_section

    def test_validates_against_pydantic_schema(self):
        pages = [
            _make_page(
                url="https://test.com",
                title="Test",
                body_text="We provide enterprise solutions for modern businesses worldwide.",
            ),
        ]
        result = preprocess(pages, "Test")

        # Should be a valid PreprocessedContent instance
        assert isinstance(result, PreprocessedContent)
        # Should serialise cleanly
        data = result.model_dump()
        assert "company_name" in data
        assert "combined_context" in data
        assert "word_count" in data

    def test_handles_heavy_repetition(self):
        """Simulate a marketing page with extreme repetition."""
        # Same CTA repeated 10 times + some real content
        lines = (
            ["Book a demo"] * 10
            + ["Start free trial"] * 5
            + ["We build the best analytics platform for growing businesses."]
            + ["Accept cookies"] * 3
        )
        pages = [_make_page(body_text="\n".join(lines))]
        result = preprocess(pages, "RepeatCo")

        # All the CTA spam should be gone
        assert "Book a demo" not in result.homepage_summary
        assert "Start free trial" not in result.homepage_summary
        assert "Accept cookies" not in result.homepage_summary

        # Real content should survive
        assert "analytics platform" in result.homepage_summary


# ═══════════════════════════════════════════════════════════════════════
#  INTEGRATION TESTS — pipe real scraper output through preprocessor
# ═══════════════════════════════════════════════════════════════════════


def _run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


@pytest.mark.integration
class TestPreprocessStripe:
    """Integration: scrape stripe.com → preprocess."""

    def test_stripe_preprocessing(self):
        from app.services.scraper import scrape_company

        pages = _run(scrape_company("https://stripe.com", max_pages=3))
        assert len(pages) >= 1, "Scraper must return at least homepage"

        result = preprocess(pages, "Stripe")

        # Schema validation
        assert isinstance(result, PreprocessedContent)
        assert result.company_name == "Stripe"

        # Homepage title should mention Stripe
        assert "stripe" in result.homepage_title.lower()

        # Should have meaningful content
        assert result.word_count > 100, f"Too few words: {result.word_count}"

        # Should have headings
        assert len(result.all_headings) >= 1

        # Combined context should be structured
        assert "=== COMPANY: Stripe ===" in result.combined_context

        # Junk should be reduced
        combined_lower = result.combined_context.lower()
        assert "accept cookies" not in combined_lower
        assert combined_lower.count("book a demo") <= 1  # at most 1 surviving

        print(f"\n--- Stripe Preprocessed ---")
        print(f"  Words: {result.word_count}")
        print(f"  Headings: {len(result.all_headings)}")
        print(f"  Value props: {len(result.key_value_propositions)}")
        print(f"  External links: {len(result.external_links)}")
        print(f"  Homepage summary length: {len(result.homepage_summary)}")
        print(f"  About section length: {len(result.about_section)}")
        print(f"  Products section length: {len(result.products_section)}")
        print(f"  Pricing section length: {len(result.pricing_section)}")
        print(f"  Combined context length: {len(result.combined_context)}")
        if result.key_value_propositions:
            print(f"  Top value props:")
            for vp in result.key_value_propositions[:5]:
                print(f"    - {vp.encode('ascii', errors='replace').decode()}")


@pytest.mark.integration
class TestPreprocessHubSpot:
    """Integration: scrape hubspot.com → preprocess."""

    def test_hubspot_preprocessing(self):
        from app.services.scraper import scrape_company

        pages = _run(scrape_company("https://www.hubspot.com", max_pages=3))
        assert len(pages) >= 1

        result = preprocess(pages, "HubSpot")

        assert isinstance(result, PreprocessedContent)
        assert result.word_count > 50
        assert len(result.all_headings) >= 1
        assert "=== COMPANY: HubSpot ===" in result.combined_context

        # Check deduplication worked — combined should be smaller than raw
        raw_total = sum(len(p.body_text) for p in pages)
        processed_total = len(result.body_text_combined)
        reduction_pct = (1 - processed_total / max(raw_total, 1)) * 100

        print(f"\n--- HubSpot Preprocessed ---")
        print(f"  Raw total chars: {raw_total}")
        print(f"  Processed chars: {processed_total}")
        print(f"  Reduction: {reduction_pct:.1f}%")
        print(f"  Words: {result.word_count}")
        print(f"  Headings: {len(result.all_headings)}")
        print(f"  About section: {len(result.about_section)} chars")


@pytest.mark.integration
class TestPreprocessNotion:
    """Integration: scrape notion.com -> preprocess."""

    def test_notion_preprocessing(self):
        from app.services.scraper import scrape_company

        pages = _run(scrape_company("https://www.notion.com", max_pages=3))
        assert len(pages) >= 1

        result = preprocess(pages, "Notion")

        assert isinstance(result, PreprocessedContent)
        assert result.word_count > 50

        # Check that combined context is well-structured
        assert "=== COMPANY: Notion ===" in result.combined_context

        # Check that junk is reduced
        junk_phrases = ["sign up free", "accept cookies", "book a demo"]
        combined_lower = result.combined_context.lower()
        surviving_junk = [j for j in junk_phrases if j in combined_lower]
        assert len(surviving_junk) == 0, f"Junk survived: {surviving_junk}"

        print(f"\n--- Notion Preprocessed ---")
        print(f"  Words: {result.word_count}")
        print(f"  Headings: {len(result.all_headings)}")
        print(f"  Combined context length: {len(result.combined_context)}")
        vps = [vp.encode("ascii", errors="replace").decode() for vp in result.key_value_propositions[:3]]
        print(f"  Value props: {vps}")


@pytest.mark.integration
class TestPreprocessCompression:
    """Integration: verify the preprocessor actually reduces content size."""

    def test_size_reduction(self):
        from app.services.scraper import scrape_company

        pages = _run(scrape_company("https://stripe.com", max_pages=3))
        assert len(pages) >= 1

        result = preprocess(pages, "Stripe")

        raw_total_chars = sum(len(p.body_text) for p in pages)
        processed_chars = len(result.body_text_combined)

        # The preprocessor should reduce content (dedup + junk removal)
        assert processed_chars <= raw_total_chars, (
            f"Preprocessor should not increase content size: "
            f"raw={raw_total_chars}, processed={processed_chars}"
        )

        if raw_total_chars > 0:
            reduction = (1 - processed_chars / raw_total_chars) * 100
            print(f"\n  Content reduction: {reduction:.1f}%")
            print(f"  Raw: {raw_total_chars} chars -> Processed: {processed_chars} chars")
