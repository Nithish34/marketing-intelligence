from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    knowledge_base_dir: str = "knowledge_base"
    log_path: str = "runs/marketing_runs.jsonl"
    output_dir: str = "outputs"
    default_channels: list[str] | None = None
    # V7: lowered from 90 to 75. The reviewer is genuinely strict, so 90 is
    # unreachable for a first-pass rule-based campaign. 75 is the "minor revision"
    # threshold that reflects real quality, not inflated scores.
    review_threshold: int = 75
    max_revision_rounds: int = 3
    max_rag_chunks: int = 5
    model_mode: str = "rule-based"
    prompt_dir: str = "prompts"
    benchmark_path: str = "benchmark_scenarios.json"
    llm_base_url: str = ""
    llm_model: str = ""
    # Agent-specific modes. None means use model_mode, keeping fresh installs deterministic.
    research_mode: str | None = None
    strategy_mode: str | None = None
    content_mode: str | None = None
    review_mode: str | None = None

    # V7: Optional Ollama mode fields for local LLM A/B testing
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    # Online LLM modes
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-1.5-flash"
    # Agent-specific Ollama models
    research_model: str = "qwen2.5:7b"
    strategy_model: str = "phi4-mini"
    content_model: str = "llama3.2:3b"
    review_model: str = "deepseek-r1:1.5b"

    @classmethod
    def load(cls, path: Path | str | None = None) -> "AppConfig":
        if path is None:
            default_path = Path("marketing_agents.config.json")
            if not default_path.exists():
                return cls()
            path = default_path

        config_path = Path(path)
        if not config_path.exists():
            return cls()

        data = json.loads(config_path.read_text(encoding="utf-8"))
        return cls(
            knowledge_base_dir=data.get("knowledge_base_dir", cls.knowledge_base_dir),
            log_path=data.get("log_path", cls.log_path),
            output_dir=data.get("output_dir", cls.output_dir),
            default_channels=data.get("default_channels"),
            review_threshold=int(data.get("review_threshold", cls.review_threshold)),
            max_revision_rounds=int(data.get("max_revision_rounds", cls.max_revision_rounds)),
            max_rag_chunks=int(data.get("max_rag_chunks", cls.max_rag_chunks)),
            model_mode=data.get("model_mode", cls.model_mode),
            prompt_dir=data.get("prompt_dir", cls.prompt_dir),
            benchmark_path=data.get("benchmark_path", cls.benchmark_path),
            llm_base_url=data.get("llm_base_url", cls.llm_base_url),
            llm_model=data.get("llm_model", cls.llm_model),
            ollama_base_url=data.get("ollama_base_url", cls.ollama_base_url),
            ollama_model=data.get("ollama_model", cls.ollama_model),
            openai_model=data.get("openai_model", cls.openai_model),
            gemini_model=data.get("gemini_model", cls.gemini_model),
            research_mode=data.get("research_mode"),
            strategy_mode=data.get("strategy_mode"),
            content_mode=data.get("content_mode"),
            review_mode=data.get("review_mode"),
            research_model=data.get("research_model", cls.research_model),
            strategy_model=data.get("strategy_model", cls.strategy_model),
            content_model=data.get("content_model", cls.content_model),
            review_model=data.get("review_model", cls.review_model),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "knowledge_base_dir": self.knowledge_base_dir,
            "log_path": self.log_path,
            "output_dir": self.output_dir,
            "default_channels": self.default_channels or ["paid social", "email", "landing page"],
            "review_threshold": self.review_threshold,
            "max_revision_rounds": self.max_revision_rounds,
            "max_rag_chunks": self.max_rag_chunks,
            "model_mode": self.model_mode,
            "prompt_dir": self.prompt_dir,
            "benchmark_path": self.benchmark_path,
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "openai_model": self.openai_model,
            "gemini_model": self.gemini_model,
            "research_mode": self.research_mode,
            "strategy_mode": self.strategy_mode,
            "content_mode": self.content_mode,
            "review_mode": self.review_mode,
            "research_model": self.research_model,
            "strategy_model": self.strategy_model,
            "content_model": self.content_model,
            "review_model": self.review_model,
        }


def write_default_config(path: Path | str = "marketing_agents.config.json") -> Path:
    config_path = Path(path)
    if not config_path.exists():
        config_path.write_text(json.dumps(AppConfig().to_dict(), indent=2), encoding="utf-8")
    return config_path
