"""Lightweight snapshot persistence layer for research quality tracking and debugging."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from pydantic import BaseModel


def sanitize_filename(name: str) -> str:
    """Sanitize company name to be lowercase, filesystem-safe, and contain no spaces."""
    # Convert to lowercase and strip whitespace
    name = name.lower().strip()
    # Replace whitespace and invalid filesystem characters with underscores
    name = re.sub(r"[^a-z0-9_-]", "_", name)
    # Remove consecutive/trailing/leading underscores
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    return name or "unknown"


def save_debug_snapshot(
    company_name: str,
    company_url: str,
    company_profile: Any,
    preprocessed_context: str,
    word_count: int,
    model_used: str,
    processing_time_seconds: float,
    pages_scraped: int,
    prompt_version: str = "v2",
    metadata: Any = None,
) -> Path:
    """Save a lightweight evaluation/debugging snapshot for research quality.

    Saves a JSON file to debug/research_outputs/ containing the company profile,
    research metadata, and extra debug details (preprocessed text preview, word count,
    latency, model used, and prompt version).
    """
    # 1. Resolve paths (relative to v2 root directory)
    app_dir = Path(__file__).resolve().parent.parent
    v2_root = app_dir.parent
    output_dir = v2_root / "debug" / "research_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Format name and timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_company = sanitize_filename(company_name)
    filename = f"{clean_company}_{timestamp}.json"
    target_path = output_dir / filename

    # 3. Serialize inputs
    profile_dict = {}
    if company_profile is not None:
        if isinstance(company_profile, BaseModel):
            profile_dict = company_profile.model_dump()
        elif isinstance(company_profile, dict):
            profile_dict = company_profile

    metadata_dict = {}
    if metadata is not None:
        if isinstance(metadata, BaseModel):
            metadata_dict = metadata.model_dump(mode="json")
        elif isinstance(metadata, dict):
            metadata_dict = metadata

    # 4. Limit preprocessed preview to 1500 chars (between 1000-2000 chars)
    preview_limit = 1500
    preview = preprocessed_context[:preview_limit] if preprocessed_context else ""
    if preprocessed_context and len(preprocessed_context) > preview_limit:
        preview += "\n... [TRUNCATED FOR PREVIEW]"

    # 5. Build full JSON payload structure
    snapshot_payload = {
        # Full ResearchOutput elements
        "company_name": company_name,
        "company_url": company_url,
        "company_profile": profile_dict,
        "metadata": metadata_dict,
        # Additional Debug Metadata
        "timestamp": datetime.now().isoformat(),
        "model_used": model_used,
        "processing_time_seconds": processing_time_seconds,
        "pages_scraped": pages_scraped,
        "preprocessed_word_count": word_count,
        "prompt_version": prompt_version,
        "preprocessed_preview": preview,
    }

    # 6. Save payload as human-readable JSON
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_payload, f, indent=2, ensure_ascii=False)

    return target_path
