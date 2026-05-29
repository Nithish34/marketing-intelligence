from __future__ import annotations

import re

from marketing_agents.contracts import BrandFacts, RetrievedContext


SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    return [sentence.strip(" \n-") for sentence in SENTENCE_RE.split(text) if sentence.strip()]


def _phrases_after_label(text: str, label: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(label)}\s*:?\s*(.*)$", re.IGNORECASE)
    lines = text.splitlines()
    matches: list[str] = []
    for index, line in enumerate(lines):
        match = pattern.search(line.strip())
        if match:
            tail = match.group(1).strip()
            if tail and tail != ":":
                matches.extend(_split_list(tail))
                continue

            for following in lines[index + 1 :]:
                stripped = following.strip()
                if not stripped or stripped == "---":
                    break
                if ":" in stripped and not stripped.startswith(("-", "*")):
                    break
                matches.extend(_split_list(stripped))
    return matches


def _split_list(text: str) -> list[str]:
    cleaned = text.strip().strip(".")
    parts = re.split(r",|\band\b", cleaned)
    return [part.strip(" .") for part in parts if part.strip(" .")]


def extract_brand_facts(context: list[RetrievedContext]) -> BrandFacts:
    if not context:
        return BrandFacts(
            value_proposition="No brand document was retrieved; use the campaign request as the source of truth.",
            voice=[],
            avoid=[],
            customer_priorities=[],
            preferred_channels=[],
            content_style=[],
            citations=["campaign_request"],
        )

    ordered_context = sorted(context, key=lambda chunk: (chunk.source, chunk.line_start or 0))
    combined = "\n\n---\n\n".join(chunk.text for chunk in ordered_context)
    sentences = _sentences(combined)
    value_proposition = next(
        (sentence for sentence in sentences if "product helps" in sentence.lower() or "helps" in sentence.lower()),
        sentences[0] if sentences else "Use retrieved brand context as source material.",
    )

    voice: list[str] = []
    avoid: list[str] = []
    customer_priorities: list[str] = []
    preferred_channels: list[str] = []
    content_style: list[str] = []

    for sentence in sentences:
        lower = sentence.lower()
        if "brand voice" in lower or "voice should be" in lower:
            voice.extend(_split_list(sentence.split("should be", 1)[-1]))
        if "avoid" in lower:
            avoid_text = re.split(r"avoid", sentence, maxsplit=1, flags=re.IGNORECASE)[-1]
            avoid.extend(_split_list(avoid_text))
        if "customers care about" in lower:
            customer_priorities.extend(_split_list(sentence.split("care about", 1)[-1]))

    preferred_channels.extend(_phrases_after_label(combined, "Primary channels"))
    content_style.extend(_phrases_after_label(combined, "Content style"))

    return BrandFacts(
        value_proposition=value_proposition,
        voice=_dedupe(voice),
        avoid=_dedupe(avoid),
        customer_priorities=_dedupe(customer_priorities),
        preferred_channels=_dedupe(preferred_channels),
        content_style=_dedupe(content_style),
        citations=[
            f"{chunk.source}:{chunk.line_start}-{chunk.line_end}" if chunk.line_start else chunk.source
            for chunk in ordered_context
        ],
    )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        key = item.lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped
