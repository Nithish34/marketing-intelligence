from __future__ import annotations

from marketing_agents.config import AppConfig
from marketing_agents.llm import HttpJsonMarketingModel, MarketingModel, RuleBasedMarketingModel
from marketing_agents.prompts import PromptLibrary


def build_model(config: AppConfig) -> MarketingModel:
    mode = config.model_mode.lower().strip()
    if mode == "rule-based":
        return RuleBasedMarketingModel()
    if mode in {"http-json", "openai-compatible"}:
        return HttpJsonMarketingModel(
            base_url=config.llm_base_url,
            model=config.llm_model,
            prompts=PromptLibrary(config.prompt_dir),
        )
    raise ValueError(f"Unknown model_mode: {config.model_mode}")
