from __future__ import annotations

from pathlib import Path


class PromptLibrary:
    def __init__(self, root: Path | str = "prompts") -> None:
        self.root = Path(root)

    def load(self, name: str) -> str:
        path = self.root / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt not found: {path}")
        return path.read_text(encoding="utf-8")

