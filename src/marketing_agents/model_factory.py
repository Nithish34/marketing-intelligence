from __future__ import annotations

from marketing_agents.config import AppConfig
from marketing_agents.llm import (
    GeminiMarketingModel,
    HttpJsonMarketingModel,
    MarketingModel,
    OllamaMarketingModel,
    OpenAIMarketingModel,
    RuleBasedMarketingModel,
)
from marketing_agents.prompts import PromptLibrary


def build_model(config: AppConfig, agent_name: str = "default") -> MarketingModel:
    agent_mode = None
    if agent_name == "research":
        agent_mode = config.research_mode
    elif agent_name == "strategy":
        agent_mode = config.strategy_mode
    elif agent_name == "content":
        agent_mode = config.content_mode
    elif agent_name == "review":
        agent_mode = config.review_mode

    mode = agent_mode or config.model_mode
    mode = mode.lower().strip()
    if mode == "rule-based":
        return RuleBasedMarketingModel()
    if mode in {"http-json", "openai-compatible"}:
        return HttpJsonMarketingModel(
            base_url=config.llm_base_url,
            model=config.llm_model,
            prompts=PromptLibrary(config.prompt_dir),
        )
    if mode == "ollama":
        safe_defaults = {
            "research": "qwen2.5:7b",
            "strategy": "phi4-mini",
            "content": "llama3.2:3b",
            "review": "deepseek-r1:1.5b",
        }
        
        if agent_name == "research":
            model = config.research_model or config.ollama_model or safe_defaults["research"]
        elif agent_name == "strategy":
            model = config.strategy_model or config.ollama_model or safe_defaults["strategy"]
        elif agent_name == "content":
            model = config.content_model or config.ollama_model or safe_defaults["content"]
        elif agent_name == "review":
            model = config.review_model or config.ollama_model or safe_defaults["review"]
        else:
            model = config.ollama_model or "qwen2.5:3b"

        return OllamaMarketingModel(
            base_url=config.ollama_base_url,
            model=model,
            prompts=PromptLibrary(config.prompt_dir),
        )
    if mode == "openai":
        return OpenAIMarketingModel(
            model=config.openai_model,
            prompts=PromptLibrary(config.prompt_dir),
        )
    if mode == "gemini":
        return GeminiMarketingModel(
            model=config.gemini_model,
            prompts=PromptLibrary(config.prompt_dir),
        )
    raise ValueError(f"Unknown model_mode: {config.model_mode}")
