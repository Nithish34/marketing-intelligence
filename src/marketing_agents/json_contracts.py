from __future__ import annotations

import json
import re
from typing import Any


class JsonContractError(ValueError):
    """Raised when model JSON cannot be parsed or repaired."""


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise JsonContractError("No JSON object found in model response")

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JsonContractError(f"Invalid JSON object: {exc}") from exc

    if not isinstance(parsed, dict):
        raise JsonContractError("Expected a JSON object")
    return parsed


def require_keys(data: dict[str, Any], required: list[str]) -> None:
    missing = [key for key in required if key not in data]
    if missing:
        raise JsonContractError(f"Missing required keys: {', '.join(missing)}")


def list_value(data: dict[str, Any], key: str, fallback: list[Any] | None = None) -> list[Any]:
    value = data.get(key, fallback or [])
    return value if isinstance(value, list) else fallback or []


def dict_value(data: dict[str, Any], key: str, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    value = data.get(key, fallback or {})
    return value if isinstance(value, dict) else fallback or {}

