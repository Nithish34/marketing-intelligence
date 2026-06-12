from __future__ import annotations

from dataclasses import dataclass


INJECTION_PATTERNS = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "developer message",
    "system prompt",
    "reveal your prompt",
    "print your instructions",
    "exfiltrate",
    "api key",
    "secret key",
    "do not follow",
    # V7: extended adversarial patterns
    "override your constraints",
    "override your instructions",
    "print the prompt",
    "reveal your training",
    "you are now dan",
    "you are now a",
    "no restrictions",
    "without restrictions",
    "jailbreak",
    "as a developer",
    "as a superuser",
    "disregard your instructions",
)


@dataclass(frozen=True)
class SafetyFinding:
    source: str
    reason: str


class SafetyError(ValueError):
    """Raised when trusted user input fails a safety check."""


def scan_untrusted_text(text: str, source: str) -> list[SafetyFinding]:
    normalized = text.lower()
    findings: list[SafetyFinding] = []
    for pattern in INJECTION_PATTERNS:
        if pattern in normalized:
            findings.append(SafetyFinding(source=source, reason=f"Matched '{pattern}'"))
    return findings


def filter_safe_context(chunks: list[tuple[str, str, int]]) -> tuple[list[tuple[str, str, int]], list[SafetyFinding]]:
    safe: list[tuple[str, str, int]] = []
    findings: list[SafetyFinding] = []

    for source, text, score in chunks:
        chunk_findings = scan_untrusted_text(text, source)
        if chunk_findings:
            findings.extend(chunk_findings)
            continue
        safe.append((source, text, score))

    return safe, findings


def validate_user_request(product: str, audience: str, goal: str) -> None:
    for name, value in {"product": product, "audience": audience, "goal": goal}.items():
        if scan_untrusted_text(value, name):
            raise SafetyError(f"{name} contains instruction-like or secret-seeking content")
