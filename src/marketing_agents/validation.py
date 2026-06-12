from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any


class ContractValidationError(ValueError):
    """Raised when an agent returns an incomplete contract."""


def require_non_empty(value: Any, name: str) -> None:
    if isinstance(value, str) and not value.strip():
        raise ContractValidationError(f"{name} must be a non-empty string")
    if isinstance(value, list) and not value:
        raise ContractValidationError(f"{name} must be a non-empty list")
    if isinstance(value, dict) and not value:
        raise ContractValidationError(f"{name} must be a non-empty object")


def validate_contract(instance: Any) -> None:
    if not is_dataclass(instance):
        raise ContractValidationError("Expected a dataclass contract instance")

    for field_info in fields(instance):
        value = getattr(instance, field_info.name)
        require_non_empty(value, field_info.name)

        type_str = str(field_info.type).replace(" ", "")
        if "list[str]" in type_str and isinstance(value, list):
            if not all(isinstance(x, str) for x in value):
                raise ContractValidationError(
                    f"{field_info.name} must be a list of plain strings, not objects or dictionaries."
                )

