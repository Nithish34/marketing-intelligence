from __future__ import annotations

import subprocess
from pathlib import Path

from marketing_agents.agents import ContentAgent, ResearchAgent, StrategyAgent
from marketing_agents.config import AppConfig
from marketing_agents.contracts import (
    CampaignPackage,
    CampaignRequest,
    RetrievedContext,
    RunDiagnostics,
    StrategyCandidate,
    ContentPackage,
    CreativeReview,
    ExecutionContext,
)
from marketing_agents.evaluation import evaluate_campaign, review_creative
from marketing_agents.llm import MarketingModel, RuleBasedMarketingModel
from marketing_agents.model_factory import build_model
from marketing_agents.observability import JsonlRunLogger
from marketing_agents.rag import LocalKnowledgeBase
from marketing_agents.safety import validate_user_request
from marketing_agents.validation import require_non_empty
from marketing_agents.memory import CampaignMemoryBank


class MarketingPipeline:
    def __init__(
        self,
        knowledge_base: LocalKnowledgeBase | None = None,
        model: MarketingModel | None = None,
        logger: JsonlRunLogger | None = None,
        config: AppConfig | None = None,
    ) -> None:
        self.config = config or AppConfig()
        self.knowledge_base = knowledge_base or LocalKnowledgeBase()
        self.logger = logger or JsonlRunLogger()
        
        self.memory_bank = CampaignMemoryBank()
        self.memory_bank.load_memories()

        if model:
            research_model = model
            strategy_model = model
            content_model = model
            review_model = model
        else:
            research_model = build_model(self.config, "research")
            strategy_model = build_model(self.config, "strategy")
            content_model = build_model(self.config, "content")
            review_model = build_model(self.config, "review")

        self.research_agent = ResearchAgent(model=research_model)
        self.strategy_agent = StrategyAgent(model=strategy_model)
        self.content_agent = ContentAgent(model=content_model)

        # Log the selected models
        self._log_model("ResearchAgent", research_model)
        self._log_model("StrategyAgent", strategy_model)
        self._log_model("ContentAgent", content_model)
        self._log_model("CreativeReview", review_model)

        # Warn about any missing Ollama models (non-blocking)
        _check_ollama_models([research_model, strategy_model, content_model, review_model])

    def _log_model(self, agent_name: str, m: MarketingModel) -> None:
        mode = "unknown"
        name = m.__class__.__name__
        if "RuleBased" in name:
            mode = "rule-based"
        elif "Ollama" in name:
            mode = "ollama"
        elif "OpenAI" in name:
            mode = "openai"
        elif "Gemini" in name:
            mode = "gemini"
        elif "HttpJson" in name:
            mode = "http-json"

        if hasattr(m, "model"):
            print(f"[{agent_name}] mode={mode} model={m.model}")
        elif isinstance(m, RuleBasedMarketingModel):
            print(f"[{agent_name}] mode={mode} model=rule-based")
        else:
            print(f"[{agent_name}] mode={mode} model=unknown")

    @classmethod
    def from_paths(
        cls,
        knowledge_base_dir: Path | str = "knowledge_base",
        log_path: Path | str = "runs/marketing_runs.jsonl",
        config: AppConfig | None = None,
    ) -> "MarketingPipeline":
        return cls(
            knowledge_base=LocalKnowledgeBase(knowledge_base_dir),
            logger=JsonlRunLogger(log_path),
            config=config,
        )

    @classmethod
    def from_config(cls, config: AppConfig) -> "MarketingPipeline":
        return cls.from_paths(
            knowledge_base_dir=config.knowledge_base_dir,
            log_path=config.log_path,
            config=config,
        )

    def run(self, request: CampaignRequest) -> CampaignPackage:
        exec_context = ExecutionContext(current_stage="validation")

        require_non_empty(request.product, "product")
        require_non_empty(request.audience, "audience")
        require_non_empty(request.goal, "goal")
        require_non_empty(request.channels, "channels")
        validate_user_request(request.product, request.audience, request.goal)
        self.logger.log("request_received", request)

        retrieved_context = self.knowledge_base.retrieve(request, limit=self.config.max_rag_chunks)
        self.logger.log("context_retrieved", retrieved_context)

        exec_context.current_stage = "research"
        research = self.research_agent.run(request, retrieved_context, exec_context)
        self.logger.log("research_completed", research)

        exec_context.current_stage = "strategy"
        strategy_candidates = self.strategy_agent.generate_candidates(request, research, exec_context)
        self.logger.log("strategy_candidates_completed", strategy_candidates)

        strategy = max(strategy_candidates, key=lambda candidate: candidate.score).strategy
        self.logger.log("strategy_completed", strategy)

        exec_context.current_stage = "content"
        content = self.content_agent.run(request, research, strategy, exec_context)
        self.logger.log("content_completed", content)

        creative_review = review_creative(
            research,
            strategy,
            content,
            iteration=1,
            threshold=self.config.review_threshold,
            original_goal=request.goal,
        )
        self.logger.log("creative_review_completed", creative_review)

        while not creative_review.passed and creative_review.iteration < self.config.max_revision_rounds:
            exec_context.previous_errors.extend(creative_review.issues)
            content = self.content_agent.revise(content, creative_review, exec_context)
            self.logger.log("content_revised", content)
            creative_review = review_creative(
                research,
                strategy,
                content,
                iteration=creative_review.iteration + 1,
                threshold=self.config.review_threshold,
                original_goal=request.goal,
            )
            self.logger.log("creative_review_recompleted", creative_review)

        evaluation = evaluate_campaign(strategy, content, creative_review)
        self.logger.log("evaluation_completed", evaluation)

        # V7: Compute per-run quality diagnostics before sealing the package.
        diagnostics = _compute_diagnostics(
            retrieved_context=retrieved_context,
            strategy_candidates=strategy_candidates,
            content=content,
            creative_review=creative_review,
            review_threshold=self.config.review_threshold,
            request_goal=request.goal,
            translated_goal=research.translated_goal,
        )
        self.logger.log("run_diagnostics_completed", diagnostics)

        package = CampaignPackage(
            request=request,
            retrieved_context=retrieved_context,
            research=research,
            strategy_candidates=strategy_candidates,
            strategy=strategy,
            content=content,
            creative_review=creative_review,
            evaluation=evaluation,
            diagnostics=diagnostics,
        )
        self.logger.log("campaign_completed", package)
        
        # Save to memory bank if successful
        self.memory_bank.save_memory(package)
        
        return package



def _check_ollama_models(models: list[MarketingModel]) -> None:
    """Warn about any Ollama models that are not pulled locally.

    Runs `ollama list` once and checks each OllamaMarketingModel's model name
    against the output. Prints a clear install hint for any that are missing.
    Does NOT crash — the pipeline continues and will fail naturally if the
    model is truly absent when Ollama is called.
    """
    from marketing_agents.llm import OllamaMarketingModel

    ollama_models = [m for m in models if isinstance(m, OllamaMarketingModel)]
    if not ollama_models:
        return

    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        available = result.stdout.lower()
    except Exception:
        # ollama not on PATH or timed out — skip silently
        return

    for m in ollama_models:
        model_name = m.model.lower().split(":")[0]  # e.g. "qwen2.5" from "qwen2.5:7b"
        if model_name not in available:
            print(
                f"\n[Warning] Missing Ollama model: {m.model}\n"
                f"  Install with: ollama pull {m.model}\n"
            )


def _compute_diagnostics(
    retrieved_context: list[RetrievedContext],
    strategy_candidates: list[StrategyCandidate],
    content: ContentPackage,
    creative_review: CreativeReview,
    review_threshold: int,
    request_goal: str,
    translated_goal: str,
) -> RunDiagnostics:
    """Compute per-run quality signals for observability.

    Each signal answers one diagnostic question:
      retrieval_quality   → "Did the KB find the right brand context?"
      strategy_diversity  → "Are the candidate strategies genuinely different?"
      content_originality → "Are the ad variants actually varied?"
      review_confidence   → "How comfortable are we with the creative quality?"
      goal_translation_used → "Did we speak customer language, not business language?"
    """
    # retrieval_quality: normalise the best chunk score to 0-100.
    # V7 weighted scoring can reach ~40+ for a strong match; we normalise to that ceiling.
    if retrieved_context:
        best_score = max(chunk.score for chunk in retrieved_context)
        retrieval_quality = min(100, round(best_score / 40 * 100))
    else:
        retrieval_quality = 0

    # strategy_diversity: ratio of unique pillar words to total pillar words across candidates.
    # A high ratio means candidates are lexically distinct — a low ratio means they converged.
    if len(strategy_candidates) >= 2:
        pillar_word_sets = [
            {
                w for p in c.strategy.messaging_pillars
                for w in p.lower().split()
                if len(w) > 4
            }
            for c in strategy_candidates
        ]
        total_unique = len(set.union(*pillar_word_sets)) if pillar_word_sets else 0
        total_all = sum(len(s) for s in pillar_word_sets)
        strategy_diversity = min(100, round(total_unique / max(total_all, 1) * 100))
    else:
        strategy_diversity = 0

    # content_originality: how varied are the ad variant openings?
    if len(content.ad_variants) < 2:
        content_originality = 0
    else:
        first_words = []
        for ad in content.ad_variants:
            text = ad.control if hasattr(ad, "control") else str(ad)
            if text.split():
                first_words.append(text.split()[0].lower())
        unique = len(set(first_words))
        content_originality = min(100, round((unique / max(len(first_words), 1)) * 100))

    # review_confidence: how far above the threshold did the creative score land?
    margin = creative_review.score - review_threshold
    if margin >= 20:
        review_confidence = 100
    elif margin >= 10:
        review_confidence = 80
    elif margin >= 0:
        review_confidence = 60
    elif margin >= -10:
        review_confidence = 30
    else:
        review_confidence = 0

    # goal_translation_used: did the customer-language goal differ from the raw business goal?
    goal_translation_used = translated_goal.strip().lower() != request_goal.strip().lower()
    
    # semantic_boost_applied: did ChromaDB contribute to retrieval?
    semantic_boost_applied = any("semantic boost" in chunk.retrieval_reason for chunk in retrieved_context)

    return RunDiagnostics(
        retrieval_quality=retrieval_quality,
        strategy_diversity=strategy_diversity,
        content_originality=content_originality,
        review_confidence=review_confidence,
        goal_translation_used=goal_translation_used,
        semantic_boost_applied=semantic_boost_applied,
    )
