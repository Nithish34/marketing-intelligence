from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from marketing_agents.contracts import CampaignRequest, RetrievedContext
from marketing_agents.safety import filter_safe_context


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
STOPWORDS = {
    "and",
    "the",
    "with",
    "for",
    "that",
    "this",
    "from",
    "into",
    "using",
    "helps",
    "product",
    "customers",
    "care",
    "about",
    "primary",
    "channels",
    "content",
    "style",
    "brand",
    "voice",
    "should",
    "avoid",
}
SEMANTIC_EXPANSIONS = {
    "students": {"academic", "assignments", "study", "exam", "college", "campus"},
    "student": {"academic", "assignments", "study", "exam", "college", "campus"},
    "signups": {"signup", "activation", "app", "onboarding"},
    "demos": {"demo", "consultation", "walkthrough"},
    "marketing": {"campaign", "copy", "channel", "ads", "email"},
    "campaign": {"marketing", "copy", "channel", "ads", "email"},
}


@dataclass(frozen=True)
class TextChunk:
    source: str
    text: str
    chunk_id: str
    line_start: int
    line_end: int


def tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) > 2 and token.lower() not in STOPWORDS
    }


def expand_tokens(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for token in tokens:
        expanded.update(SEMANTIC_EXPANSIONS.get(token, set()))
    return expanded


class LocalKnowledgeBase:
    def __init__(self, root: Path | str = "knowledge_base") -> None:
        self.root = Path(root)

    def retrieve(self, request: CampaignRequest, limit: int = 5) -> list[RetrievedContext]:
        query = " ".join([request.product, request.audience, request.goal, request.tone, " ".join(request.channels)])
        query_tokens = expand_tokens(tokenize(query))
        candidates: list[tuple[str, str, int]] = []

        if not self.root.exists():
            return []

        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in {".txt", ".md"} or not path.is_file():
                continue
            for chunk in self._chunk_file(path):
                chunk_tokens = tokenize(chunk.text)
                overlap = query_tokens.intersection(chunk_tokens)
                score = self._score_chunk(request, chunk.text, overlap)
                if score > 0:
                    reason = self._reason(overlap, request, chunk.text)
                    source = f"{chunk.source}:{chunk.line_start}-{chunk.line_end}"
                    payload = self._pack_chunk(chunk, reason)
                    candidates.append((source, payload, score))

        safe_candidates, _findings = filter_safe_context(candidates)
        safe_candidates = self._filter_low_relevance_documents(safe_candidates)
        ranked_all = sorted(safe_candidates, key=lambda item: item[2], reverse=True)
        if ranked_all:
            top_score = ranked_all[0][2]
            threshold = max(1, top_score // 2)
            ranked_all = [
                item
                for item in ranked_all
                if item[2] >= threshold or self._contains_brand_fact_label(item[1])
            ]
        ranked = ranked_all[:limit]
        contexts: list[RetrievedContext] = []
        for source, text, score in ranked:
            chunk = self._unpack_chunk(source, text)
            contexts.append(
                RetrievedContext(
                    source=chunk.source,
                    text=chunk.text,
                    score=score,
                    chunk_id=chunk.chunk_id,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    retrieval_reason=chunk.retrieval_reason,
                )
            )
        return contexts

    def _filter_low_relevance_documents(self, candidates: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
        if not candidates:
            return []

        doc_scores: dict[str, int] = {}
        for source, _text, score in candidates:
            doc = source.split(":", 1)[0]
            doc_scores[doc] = doc_scores.get(doc, 0) + score

        top_doc_score = max(doc_scores.values())
        threshold = max(1, (top_doc_score * 3 + 4) // 5)
        return [
            item for item in candidates
            if doc_scores[item[0].split(":", 1)[0]] >= threshold
        ]

    def _chunk_file(self, path: Path, max_lines: int = 8) -> list[TextChunk]:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        chunks: list[TextChunk] = []
        current: list[str] = []
        start = 1

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            starts_new_section = stripped.startswith("#") or (":" in stripped and len(stripped) < 80)
            if current and (not stripped or starts_new_section or len(current) >= max_lines):
                chunks.append(self._make_chunk(path, current, start, index - 1, len(chunks)))
                current = []
                start = index
            if stripped:
                current.append(line)

        if current:
            chunks.append(self._make_chunk(path, current, start, len(lines), len(chunks)))
        return chunks

    def _make_chunk(self, path: Path, lines: list[str], start: int, end: int, index: int) -> TextChunk:
        return TextChunk(
            source=str(path),
            text="\n".join(lines)[:1200],
            chunk_id=f"{path.stem}-{index + 1}",
            line_start=start,
            line_end=end,
        )

    def _score_chunk(self, request: CampaignRequest, text: str, overlap: set[str]) -> int:
        lower = text.lower()
        channel_tokens = tokenize(" ".join(request.channels))
        has_core_overlap = bool(overlap - channel_tokens)
        has_request_phrase = any(
            phrase and phrase.lower() in lower
            for phrase in (request.product, request.audience, request.goal)
        )
        score = len(overlap) * 2
        for phrase in (request.product, request.audience, request.goal):
            if phrase and phrase.lower() in lower:
                score += 4
        for channel in request.channels:
            if channel.lower() in lower:
                score += 2
        if "avoid" in lower or "brand voice" in lower or "customers care about" in lower:
            score += 3
        if channel_tokens and overlap and not has_core_overlap and not has_request_phrase:
            score = min(score, 2)
        return score

    def _contains_brand_fact_label(self, packed_text: str) -> bool:
        lower = packed_text.lower()
        return any(
            label in lower
            for label in ("brand voice", "customers care about", "primary channels", "content style", "avoid")
        )

    def _reason(self, overlap: set[str], request: CampaignRequest, text: str) -> str:
        reasons: list[str] = []
        if overlap:
            reasons.append(f"matched terms: {', '.join(sorted(overlap)[:6])}")
        if request.audience.lower() in text.lower():
            reasons.append("matched audience phrase")
        if any(channel.lower() in text.lower() for channel in request.channels):
            reasons.append("matched requested channel")
        return "; ".join(reasons) or "hybrid lexical match"

    def _pack_chunk(self, chunk: TextChunk, reason: str) -> str:
        return "\n".join(
            [
                f"__chunk_id__={chunk.chunk_id}",
                f"__line_start__={chunk.line_start}",
                f"__line_end__={chunk.line_end}",
                f"__reason__={reason}",
                chunk.text,
            ]
        )

    def _unpack_chunk(self, source: str, packed: str) -> RetrievedContext:
        lines = packed.splitlines()
        metadata = {}
        body_start = 0
        for index, line in enumerate(lines):
            if not line.startswith("__"):
                body_start = index
                break
            key, value = line.split("=", 1)
            key = key.removeprefix("__").removesuffix("__")
            metadata[key] = value
        source_path = source.rsplit(":", 1)[0]
        return RetrievedContext(
            source=source_path,
            text="\n".join(lines[body_start:]),
            score=0,
            chunk_id=metadata.get("chunk_id", ""),
            line_start=int(metadata.get("line_start", "0")),
            line_end=int(metadata.get("line_end", "0")),
            retrieval_reason=metadata.get("reason", ""),
        )
