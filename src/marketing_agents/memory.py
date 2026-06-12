import json
import logging
from pathlib import Path
from marketing_agents.contracts import CampaignPackage

_log = logging.getLogger(__name__)

class CampaignMemoryBank:
    def __init__(self, storage_dir: Path | str = "memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.memories = []

    def load_memories(self):
        self.memories = []
        for path in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.memories.append(data)
            except Exception as e:
                _log.warning(f"Failed to load memory {path}: {e}")

    def save_memory(self, package: CampaignPackage):
        """Save campaigns that scored > 90 to memory bank."""
        if package.creative_review.score >= 90:
            safe_product = "".join(c for c in package.request.product if c.isalnum() or c == "_")
            safe_aud = "".join(c for c in package.request.audience if c.isalnum() or c == "_")
            filename = f"{safe_product}_{safe_aud}.json"
            filepath = self.storage_dir / filename
            try:
                filepath.write_text(json.dumps(package.to_dict(), default=str, indent=2), encoding="utf-8")
                _log.info(f"Saved successful campaign to memory: {filepath}")
            except Exception as e:
                _log.warning(f"Failed to save memory: {e}")
