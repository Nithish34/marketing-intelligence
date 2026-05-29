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
    review_threshold: int = 90
    max_revision_rounds: int = 3
    max_rag_chunks: int = 5
    model_mode: str = "rule-based"
    prompt_dir: str = "prompts"
    benchmark_path: str = "benchmark_scenarios.json"
    llm_base_url: str = ""
    llm_model: str = ""

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
        }


def write_default_config(path: Path | str = "marketing_agents.config.json") -> Path:
    config_path = Path(path)
    if not config_path.exists():
        config_path.write_text(json.dumps(AppConfig().to_dict(), indent=2), encoding="utf-8")
    return config_path
