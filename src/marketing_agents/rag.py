from __future__ import annotations

import hashlib
import json
import re
import logging
from dataclasses import dataclass
from pathlib import Path

from marketing_agents.contracts import CampaignRequest, RetrievedContext
from marketing_agents.safety import filter_safe_context

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

_log = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
STOPWORDS = {
    "and", "the", "with", "for", "that", "this", "from", "into", "using", 
    "helps", "product", "customers", "care", "about", "primary", "channels", 
    "content", "style", "brand", "voice", "should", "avoid",
}
SEMANTIC_EXPANSIONS = {
    "students": {"academic", "assignments", "study", "exam", "college", "campus"},
    "student": {"academic", "assignments", "study", "exam", "college", "campus"},
    "signups": {"signup", "activation", "app", "onboarding"},
    "demos": {"demo", "consultation", "walkthrough"},
    "marketing": {"campaign", "copy", "channel", "ads", "email"},
    "campaign": {"marketing", "copy", "channel", "ads", "email"},
}

FIELD_WEIGHTS: dict[str, int] = {
    "audience": 4,  
    "product":  3,  
    "goal":     3,  
    "tone":     2,  
}

MIN_ABSOLUTE_SCORE: int = 4
MIN_CHUNK_CHARS: int = 200
MAX_CHUNK_CHARS: int = 500
CACHE_DIR: str = ".chroma_cache"

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
    def __init__(self, root: Path | str = "knowledge_base", cache_dir: Path | str = CACHE_DIR) -> None:
        self.root = Path(root)
        self._cache_dir = Path(cache_dir)
        self.chroma_client = None
        self.collection = None
        
        if CHROMA_AVAILABLE and self.root.exists():
            try:
                self._init_chroma()
            except Exception as e:
                _log.warning(f"ChromaDB initialization failed, falling back to pure lexical: {e}")
                self.chroma_client = None
                self.collection = None

    # --- Persistent cache with hash invalidation ---

    def _kb_hash(self) -> str:
        """SHA-256 hash of every file's path + content in the knowledge base."""
        h = hashlib.sha256()
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in {".txt", ".md"} or not path.is_file():
                continue
            h.update(str(path.relative_to(self.root)).encode())
            h.update(path.read_bytes())
        return h.hexdigest()

    def _init_chroma(self) -> None:
        """Load cached Chroma DB or rebuild if knowledge base changed."""
        current_hash = self._kb_hash()
        hash_file = self._cache_dir / "kb_hash.txt"
        persist_dir = self._cache_dir / "chroma_db"

        # Check if cached index is still valid
        cache_valid = (
            persist_dir.exists()
            and hash_file.exists()
            and hash_file.read_text(encoding="utf-8").strip() == current_hash
        )

        if cache_valid:
            _log.info("[RAG] Loading cached Chroma index (KB unchanged)")
            self.chroma_client = chromadb.PersistentClient(path=str(persist_dir))
            self.collection = self.chroma_client.get_or_create_collection(name="marketing_kb")
            if self.collection.count() > 0:
                return
            # Cache dir exists but collection is empty — fall through to rebuild

        _log.info("[RAG] Rebuilding Chroma index (KB changed or first run)")
        # Clean stale cache
        if persist_dir.exists():
            import shutil
            shutil.rmtree(persist_dir, ignore_errors=True)

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.chroma_client.get_or_create_collection(name="marketing_kb")
        self._index_all()

        # Save hash so next run skips rebuild
        hash_file.write_text(current_hash, encoding="utf-8")

    def _index_all(self) -> None:
        if not self.collection:
            return
            
        docs = []
        metadatas = []
        ids = []
        
        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in {".txt", ".md"} or not path.is_file():
                continue
            for chunk in self._chunk_file(path):
                docs.append(chunk.text)
                metadatas.append({
                    "source": chunk.source,
                    "chunk_id": chunk.chunk_id,
                    "line_start": chunk.line_start,
                    "line_end": chunk.line_end
                })
                ids.append(chunk.chunk_id)
                
        if docs:
            self.collection.add(documents=docs, metadatas=metadatas, ids=ids)

    def retrieve(self, request: CampaignRequest, limit: int = 5) -> list[RetrievedContext]:
        # Semantic Search Boost
        semantic_scores = {}
        if self.collection and self.collection.count() > 0:
            query = f"{request.product} {request.audience} {request.goal}"
            try:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=min(limit * 2, self.collection.count())
                )
                if results and results.get("ids") and results["ids"][0]:
                    for i, doc_id in enumerate(results["ids"][0]):
                        # Closer to 0 is better distance in chroma default (L2).
                        # We grant up to 8 bonus points for strong semantic similarity.
                        dist = results["distances"][0][i] if "distances" in results and results["distances"] else 1.0
                        bonus = max(0, int(8 - dist * 4)) 
                        semantic_scores[doc_id] = bonus
            except Exception as e:
                _log.warning(f"Semantic search failed: {e}")

        # Lexical Search
        query_str = " ".join([request.product, request.audience, request.goal, request.tone, " ".join(request.channels)])
        query_tokens = expand_tokens(tokenize(query_str))
        candidates: list[tuple[str, str, int]] = []

        if not self.root.exists():
            return []

        for path in sorted(self.root.rglob("*")):
            if path.suffix.lower() not in {".txt", ".md"} or not path.is_file():
                continue
            for chunk in self._chunk_file(path):
                chunk_tokens = tokenize(chunk.text)
                overlap = query_tokens.intersection(chunk_tokens)
                
                lexical_score = self._score_chunk(request, chunk.text, overlap)
                semantic_boost = semantic_scores.get(chunk.chunk_id, 0)
                final_score = lexical_score + semantic_boost
                
                if final_score > 0:
                    reason = self._reason(overlap, request, chunk.text)
                    if semantic_boost > 0:
                        reason += f"; semantic boost +{semantic_boost}"
                    source = f"{chunk.source}:{chunk.line_start}-{chunk.line_end}"
                    payload = self._pack_chunk(chunk, reason)
                    candidates.append((source, payload, final_score))

        safe_candidates, _findings = filter_safe_context(candidates)
        safe_candidates = [
            item for item in safe_candidates
            if item[2] >= MIN_ABSOLUTE_SCORE or self._contains_brand_fact_label(item[1])
        ]
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

    def _chunk_file(self, path: Path) -> list[TextChunk]:
        """Semantic section chunking: split on headings / blank-line boundaries,
        then merge small adjacent sections to hit the 250-450 char target."""
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        # --- Phase 1: split into raw sections by heading or blank line ---
        raw_sections: list[tuple[int, int, list[str]]] = []  # (start, end, lines)
        current: list[str] = []
        start = 1

        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            is_boundary = (
                not stripped
                or stripped.startswith("#")
                or (":" in stripped and len(stripped) < 80 and not current)
            )
            if current and is_boundary:
                raw_sections.append((start, index - 1, current))
                current = []
                start = index
                if stripped and not stripped.startswith("#"):
                    current.append(line)
                    continue
            if stripped:
                if not current:
                    start = index
                current.append(line)

        if current:
            raw_sections.append((start, len(lines), current))

        # --- Phase 2: merge small sections to reach MIN_CHUNK_CHARS ---
        merged: list[tuple[int, int, list[str]]] = []
        buf_start = 0
        buf_end = 0
        buf_lines: list[str] = []

        for sec_start, sec_end, sec_lines in raw_sections:
            candidate_text = "\n".join(buf_lines + sec_lines)
            if not buf_lines:
                buf_start, buf_end, buf_lines = sec_start, sec_end, list(sec_lines)
            elif len(candidate_text) <= MAX_CHUNK_CHARS:
                buf_end = sec_end
                buf_lines.extend(sec_lines)
            else:
                merged.append((buf_start, buf_end, buf_lines))
                buf_start, buf_end, buf_lines = sec_start, sec_end, list(sec_lines)

        if buf_lines:
            merged.append((buf_start, buf_end, buf_lines))

        # --- Phase 3: emit TextChunks ---
        chunks: list[TextChunk] = []
        for idx, (sec_start, sec_end, sec_lines) in enumerate(merged):
            chunks.append(self._make_chunk(path, sec_lines, sec_start, sec_end, idx))
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
        score = 0

        for field_name, weight in FIELD_WEIGHTS.items():
            value = getattr(request, field_name, "")
            if isinstance(value, list):
                value = " ".join(value)
            field_tokens = tokenize(value)
            field_hits = field_tokens.intersection(tokenize(lower))
            if field_hits:
                score += len(field_hits) * weight
            if value and value.lower() in lower:
                score += weight * 2

        for channel in request.channels:
            if channel.lower() in lower:
                score += 1

        if "avoid" in lower or "brand voice" in lower or "customers care about" in lower:
            score += 3

        has_core_overlap = bool(overlap - channel_tokens)
        has_request_phrase = any(
            phrase and phrase.lower() in lower
            for phrase in (request.product, request.audience, request.goal)
        )
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
