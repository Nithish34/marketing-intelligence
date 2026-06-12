"""Tests for the Gemini-backed company profile extraction layer.

These tests use deterministic fake Gemini clients. They validate reliability and
business-understanding guardrails without requiring network access or API keys.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.research import CompanyProfile, PreprocessedContent
from app.services.llm_client import (
    EmptyResponseError,
    GeminiRateLimitError,
    InvalidJSONError,
    OutputValidationError,
    _build_prompt,
    _parse_response,
    _validate_output,
    analyze_company,
)


class FakeModels:
    def __init__(self, payload: dict | str | None, *, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls: list[dict] = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.payload is None:
            return SimpleNamespace(text="")
        if isinstance(self.payload, str):
            return SimpleNamespace(text=self.payload)
        return SimpleNamespace(
            text=json.dumps(self.payload),
            usage_metadata=SimpleNamespace(
                prompt_token_count=100,
                candidates_token_count=50,
                total_token_count=150,
            ),
        )


class FakeClient:
    def __init__(self, payload: dict | str | None, *, error: Exception | None = None):
        self.aio = SimpleNamespace(models=FakeModels(payload, error=error))


class RateLimitException(Exception):
    status_code = 429


def _content_for(company: str) -> PreprocessedContent:
    fixtures = {
        "Stripe": PreprocessedContent(
            company_name="Stripe",
            homepage_title="Stripe | Financial Infrastructure for the Internet",
            meta_description="Stripe is a suite of APIs powering online payment processing and commerce.",
            homepage_summary=(
                "Financial infrastructure for the internet. Millions of businesses use Stripe "
                "to accept payments, manage subscriptions, prevent fraud, and expand globally."
            ),
            products_section=(
                "Products include Payments, Billing, Checkout, Radar fraud prevention, "
                "Connect for marketplaces, and embedded financial services."
            ),
            key_value_propositions=[
                "Financial infrastructure for the internet",
                "Online payments for internet businesses",
            ],
            combined_context=(
                "Stripe helps developers and businesses accept online payments, manage billing, "
                "reduce fraud, and build financial products through APIs."
            ),
            word_count=48,
        ),
        "HubSpot": PreprocessedContent(
            company_name="HubSpot",
            homepage_title="HubSpot CRM Platform",
            meta_description="Marketing, sales, service, content, and operations software.",
            homepage_summary=(
                "HubSpot's customer platform connects marketing, sales, service, content, "
                "operations, and commerce teams around a shared CRM."
            ),
            products_section=(
                "Products include Marketing Hub, Sales Hub, Service Hub, Content Hub, "
                "Operations Hub, Commerce Hub, and Smart CRM."
            ),
            key_value_propositions=[
                "Customer platform with all the software, integrations, and resources you need",
                "Marketing, sales, and service software built on a CRM",
            ],
            combined_context=(
                "HubSpot provides CRM software for marketing teams, sales teams, service teams, "
                "and growing businesses that need customer data in one platform."
            ),
            word_count=47,
        ),
        "Notion": PreprocessedContent(
            company_name="Notion",
            homepage_title="Notion - The connected workspace",
            meta_description="A workspace for docs, projects, knowledge, and AI.",
            homepage_summary=(
                "Notion is a connected workspace where teams write docs, manage projects, "
                "organize company knowledge, and use AI in one flexible tool."
            ),
            products_section=(
                "Products include docs, wikis, project management, calendar, forms, sites, "
                "and Notion AI for knowledge work."
            ),
            key_value_propositions=[
                "Your connected workspace for docs, projects, and knowledge",
                "Centralize knowledge and manage teamwork",
            ],
            combined_context=(
                "Notion helps individuals and teams create a flexible workspace for notes, "
                "documents, project tracking, databases, and knowledge management."
            ),
            word_count=45,
        ),
    }
    return fixtures[company]


def _profile_payload(company: str) -> dict:
    payloads = {
        "Stripe": {
            "business_summary": (
                "Stripe provides financial infrastructure for businesses that need to accept "
                "payments, manage billing, reduce fraud, and build commerce workflows online."
            ),
            "products_services": [
                "online payments",
                "billing",
                "checkout",
                "fraud prevention",
                "embedded finance",
            ],
            "target_audience": [
                "developers",
                "online businesses",
                "startups",
                "enterprise commerce teams",
            ],
            "brand_tone": ["professional", "technical", "developer-friendly", "trustworthy"],
            "usp": (
                "Stripe offers developer-first APIs and financial infrastructure that help "
                "businesses operate payments and commerce globally."
            ),
            "industry_category": "Fintech / Payments Infrastructure",
        },
        "HubSpot": {
            "business_summary": (
                "HubSpot provides a CRM-centered customer platform for marketing, sales, "
                "service, content, operations, and commerce teams."
            ),
            "products_services": [
                "CRM",
                "marketing automation",
                "sales software",
                "customer service software",
                "content management",
            ],
            "target_audience": [
                "marketing teams",
                "sales teams",
                "service teams",
                "growing businesses",
            ],
            "brand_tone": ["helpful", "approachable", "business-focused", "educational"],
            "usp": (
                "HubSpot unifies customer-facing teams on a connected CRM platform with "
                "integrated hubs for growth."
            ),
            "industry_category": "Marketing Technology / CRM",
        },
        "Notion": {
            "business_summary": (
                "Notion provides a connected workspace for notes, docs, project management, "
                "wikis, and team knowledge management."
            ),
            "products_services": [
                "docs",
                "wikis",
                "project management",
                "knowledge management",
                "workspace AI",
            ],
            "target_audience": [
                "knowledge workers",
                "teams",
                "startups",
                "project managers",
            ],
            "brand_tone": ["clear", "flexible", "modern", "collaborative"],
            "usp": (
                "Notion combines documentation, projects, databases, and knowledge management "
                "in one flexible workspace."
            ),
            "industry_category": "Productivity / Workspace Software",
        },
    }
    return payloads[company]


def _joined_profile_text(profile: CompanyProfile) -> str:
    return " ".join(
        [
            profile.business_summary,
            " ".join(profile.products_services),
            " ".join(profile.target_audience),
            " ".join(profile.brand_tone),
            profile.usp,
            profile.industry_category,
        ]
    ).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("company", "expected_terms"),
    [
        ("Stripe", ["fintech", "payments", "developer"]),
        ("HubSpot", ["marketing", "crm", "sales"]),
        ("Notion", ["productivity", "workspace", "knowledge management"]),
    ],
)
async def test_analyze_company_returns_reasonable_company_profile(company, expected_terms):
    client = FakeClient(_profile_payload(company))

    profile = await analyze_company(
        _content_for(company),
        client=client,
        model="gemini-2.5-flash",
        generation_config=SimpleNamespace(test_config=True),
    )

    assert isinstance(profile, CompanyProfile)
    assert profile.business_summary
    assert profile.products_services
    assert profile.target_audience
    assert profile.brand_tone
    assert profile.usp
    assert profile.industry_category

    text = _joined_profile_text(profile)
    for term in expected_terms:
        assert term in text

    call = client.aio.models.calls[0]
    assert call["model"] == "gemini-2.5-flash"
    assert "Return valid JSON only" in call["contents"]
    assert "Cleaned website context" in call["contents"]


def test_build_prompt_contains_schema_and_cleaned_context_only():
    content = _content_for("Stripe")

    prompt = _build_prompt(content)

    assert "senior business analyst" in prompt
    assert "Return valid JSON only" in prompt
    assert "business_summary" in prompt
    assert "Stripe" in prompt
    assert "<html" not in prompt.lower()
    assert "code fences" in prompt


def test_parse_response_accepts_json_object():
    parsed = _parse_response(json.dumps(_profile_payload("Stripe")))

    assert parsed["industry_category"] == "Fintech / Payments Infrastructure"


def test_parse_response_rejects_markdown_or_invalid_json():
    with pytest.raises(InvalidJSONError):
        _parse_response("```json\n{\"business_summary\": \"Nope\"}\n```")


def test_parse_response_rejects_non_object_json():
    with pytest.raises(InvalidJSONError):
        _parse_response("[1, 2, 3]")


def test_validate_output_rejects_missing_required_fields():
    with pytest.raises(OutputValidationError):
        _validate_output(
            {"business_summary": "Missing everything else."},
            raw_response='{"business_summary": "Missing everything else."}',
        )


@pytest.mark.asyncio
async def test_analyze_company_rejects_empty_response():
    client = FakeClient(None)

    with pytest.raises(EmptyResponseError):
        await analyze_company(
            _content_for("Stripe"),
            client=client,
            model="gemini-2.5-flash",
            generation_config=SimpleNamespace(test_config=True),
        )


@pytest.mark.asyncio
async def test_analyze_company_classifies_rate_limit_errors():
    client = FakeClient(None, error=RateLimitException("quota exceeded"))

    with pytest.raises(GeminiRateLimitError):
        await analyze_company(
            _content_for("Stripe"),
            client=client,
            model="gemini-2.5-flash",
            generation_config=SimpleNamespace(test_config=True),
        )
