from __future__ import annotations

import re
from pathlib import Path

from marketing_agents.contracts import CampaignRequest, RetrievedContext
from marketing_agents.safety import filter_safe_context


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def tokenize(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text) if len(token) > 2}


class LocalKnowledgeBase:
    def __init__(self, root: Path | str = "knowledge_base") -> None:
        self.root = Path(root)

    def retrieve(self, request: CampaignRequest, limit: int = 5) -> list[RetrievedContext]:
        query = " ".join([request.product, request.audience, request.goal, request.tone, " ".join(request.channels)])
        query_tokens = tokenize(query)
        candidates: list[tuple[str, str, int]] = []

        if not self.root.exists():
            return []

        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in {".txt", ".md"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            score = len(query_tokens.intersection(tokenize(text)))
            if score > 0:
                candidates.append((str(path), text[:2000], score))

        safe_candidates, _findings = filter_safe_context(candidates)
        ranked = sorted(safe_candidates, key=lambda item: item[2], reverse=True)[:limit]
        return [RetrievedContext(source=source, text=text, score=score) for source, text, score in ranked]

