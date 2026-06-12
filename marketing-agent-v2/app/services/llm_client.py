"""Gemini client for structured company profile extraction.

This module is intentionally narrow: it converts PreprocessedContent into a
validated CompanyProfile. It does not orchestrate jobs, touch the database, or
create downstream research/strategy/content agents.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.schemas.research import CompanyProfile, PreprocessedContent


logger = logging.getLogger(__name__)


DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_P = 0.8
RESPONSE_MIME_TYPE = "application/json"


class LLMClientError(RuntimeError):
    """Base class for all LLM client failures."""


class GeminiConfigurationError(LLMClientError):
    """Raised when Gemini cannot be called because configuration is missing."""


class GeminiTimeoutError(LLMClientError):
    """Raised when the Gemini call times out."""


class GeminiRateLimitError(LLMClientError):
    """Raised when Gemini rejects the request due to rate limiting."""


class GeminiAPIError(LLMClientError):
    """Raised for non-timeout, non-rate-limit Gemini API failures."""


class EmptyResponseError(LLMClientError):
    """Raised when Gemini returns no usable response text."""


class InvalidJSONError(LLMClientError):
    """Raised when Gemini returns text that is not valid JSON."""


class OutputValidationError(LLMClientError):
    """Raised when parsed JSON does not match CompanyProfile."""


def _build_prompt(content: PreprocessedContent) -> str:
    """Build the analyst prompt from cleaned, high-signal website content."""
    schema = {
        "business_summary": "2-3 sentence summary of what the company does, who it serves, and its core value.",
        "products_services": ["5-8 high-level business offerings or product categories. Avoid exhaustive feature lists — prefer strategic business categories over implementation details (e.g. 'payments', 'billing', 'fraud prevention', not a detailed list of every capability)."],
        "target_audience": ["3-7 core customer segments. Avoid generic audiences like 'everyone' or 'all businesses'. Prefer specific, strategically useful segments (e.g. 'online businesses', 'developers', 'startups', 'enterprise commerce teams')."],
        "brand_tone": ["3-5 concise adjectives describing the apparent communication style."],
        "usp": "1-2 sentence unique selling proposition grounded in the website context.",
        "industry_category": "Concise industry/category label.",
    }
    context = content.model_dump(mode="json")

    return "\n".join(
        [
            "You are a senior business analyst and market researcher.",
            "Your task is to extract structured business intelligence from cleaned website content.",
            "",
            "Return valid JSON only. Do not include markdown, code fences, commentary, or prose outside JSON.",
            "Use conservative inference. Do not invent products, services, audiences, or claims that are not supported by the context.",
            "Prefer specificity over vague labels, but only when the source context supports it.",
            "",
            "Required JSON schema:",
            json.dumps(schema, indent=2),
            "",
            "Analysis goals:",
            "1. Identify what the company actually does.",
            "2. Identify 5-8 high-level products or service categories. Group related capabilities into strategic business categories rather than listing every individual feature or sub-product.",
            "3. Infer 3-7 core target audience segments from positioning, pages, and value propositions. Be specific and strategically useful — avoid overly broad segments.",
            "4. Describe the apparent brand tone.",
            "5. Identify the unique selling proposition.",
            "6. Classify the industry/category.",
            "",
            "Cleaned website context:",
            json.dumps(context, ensure_ascii=False, indent=2),
        ]
    )


def _build_generation_config() -> Any:
    """Create Gemini generation config without leaking SDK details elsewhere."""
    try:
        from google.genai import types
    except ImportError as exc:
        raise GeminiConfigurationError(
            "google-genai is not installed. Install project dependencies before calling Gemini."
        ) from exc

    return types.GenerateContentConfig(
        temperature=getattr(settings, "llm_temperature", DEFAULT_TEMPERATURE),
        top_p=DEFAULT_TOP_P,
        max_output_tokens=getattr(settings, "llm_max_output_tokens", 4096),
        response_mime_type=RESPONSE_MIME_TYPE,
    )


def _build_client() -> Any:
    """Create the real Gemini client from app settings."""
    if not settings.gemini_api_key:
        raise GeminiConfigurationError("GEMINI_API_KEY is required for analyze_company().")

    try:
        from google import genai
    except ImportError as exc:
        raise GeminiConfigurationError(
            "google-genai is not installed. Install project dependencies before calling Gemini."
        ) from exc

    return genai.Client(api_key=settings.gemini_api_key)


async def _call_gemini(
    prompt: str,
    *,
    client: Any,
    model: str,
    generation_config: Any | None = None,
) -> Any:
    """Call Gemini and return the raw SDK response."""
    config = generation_config if generation_config is not None else _build_generation_config()

    try:
        if hasattr(client, "aio") and hasattr(client.aio, "models"):
            return await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

        if hasattr(client, "models"):
            return await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=prompt,
                config=config,
            )
    except (asyncio.TimeoutError, TimeoutError) as exc:
        logger.exception("Gemini request timed out", extra={"model": model})
        raise GeminiTimeoutError(f"Gemini request timed out for model {model}.") from exc
    except Exception as exc:
        _raise_api_error(exc, model=model)

    raise GeminiConfigurationError(
        "Gemini client must expose either client.aio.models.generate_content or client.models.generate_content."
    )


def _raise_api_error(exc: Exception, *, model: str) -> None:
    """Classify SDK exceptions into typed client errors."""
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    message = str(exc)

    logger.exception(
        "Gemini request failed",
        extra={"model": model, "status_code": status_code, "error": message},
    )

    if status_code == 429 or "rate limit" in message.lower() or "quota" in message.lower():
        raise GeminiRateLimitError(f"Gemini rate limit or quota error for model {model}: {message}") from exc

    raise GeminiAPIError(f"Gemini API error for model {model}: {message}") from exc


def _extract_text(response: Any) -> str:
    """Extract response text from the Gemini SDK response shape."""
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) if content is not None else None
        for part in parts or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                return part_text.strip()

    raise EmptyResponseError("Gemini returned an empty response.")


def _parse_response(raw_response: str) -> dict[str, Any]:
    """Parse the JSON-only model response."""
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        logger.error(
            "Gemini returned invalid JSON",
            extra={"raw_model_response": raw_response, "json_error": str(exc)},
        )
        raise InvalidJSONError(f"Gemini returned invalid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        logger.error("Gemini JSON response was not an object", extra={"raw_model_response": raw_response})
        raise InvalidJSONError("Gemini JSON response must be an object.")

    return parsed


def _validate_output(data: dict[str, Any], *, raw_response: str) -> CompanyProfile:
    """Validate parsed data against the CompanyProfile schema."""
    try:
        profile = CompanyProfile.model_validate(data)
    except ValidationError as exc:
        logger.error(
            "Gemini response failed CompanyProfile validation",
            extra={"raw_model_response": raw_response, "validation_error": str(exc)},
        )
        raise OutputValidationError(f"CompanyProfile validation failed: {exc}") from exc

    logger.info("CompanyProfile validation succeeded")
    return profile


def _token_usage(response: Any) -> dict[str, int | None]:
    """Extract token usage metadata when the SDK provides it."""
    usage = getattr(response, "usage_metadata", None)
    return {
        "prompt_tokens": getattr(usage, "prompt_token_count", None),
        "candidate_tokens": getattr(usage, "candidates_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
    }


async def analyze_company(
    content: PreprocessedContent,
    *,
    client: Any | None = None,
    model: str | None = None,
    generation_config: Any | None = None,
) -> CompanyProfile:
    """Analyze cleaned website content and return a validated CompanyProfile."""
    selected_model = model or settings.gemini_model
    gemini_client = client or _build_client()
    prompt = _build_prompt(content)
    started_at = time.perf_counter()

    logger.info(
        "Starting company profile analysis",
        extra={"model": selected_model, "company_name": content.company_name},
    )

    response = await _call_gemini(
        prompt,
        client=gemini_client,
        model=selected_model,
        generation_config=generation_config,
    )
    latency = time.perf_counter() - started_at
    raw_response = _extract_text(response)
    usage = _token_usage(response)

    logger.info(
        "Gemini response received",
        extra={
            "model": selected_model,
            "latency_seconds": round(latency, 3),
            **usage,
        },
    )

    parsed = _parse_response(raw_response)
    return _validate_output(parsed, raw_response=raw_response)
