from __future__ import annotations

from pathlib import Path

from marketing_agents.agents import ContentAgent, ResearchAgent, StrategyAgent
from marketing_agents.config import AppConfig
from marketing_agents.contracts import CampaignPackage, CampaignRequest
from marketing_agents.evaluation import evaluate_campaign, review_creative
from marketing_agents.llm import MarketingModel, RuleBasedMarketingModel
from marketing_agents.model_factory import build_model
from marketing_agents.observability import JsonlRunLogger
from marketing_agents.rag import LocalKnowledgeBase
from marketing_agents.safety import validate_user_request
from marketing_agents.validation import require_non_empty


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
        self.model = model or (build_model(self.config) if self.config.model_mode != "rule-based" else RuleBasedMarketingModel())
        self.logger = logger or JsonlRunLogger()
        self.research_agent = ResearchAgent(self.model)
        self.strategy_agent = StrategyAgent(self.model)
        self.content_agent = ContentAgent(self.model)

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
        require_non_empty(request.product, "product")
        require_non_empty(request.audience, "audience")
        require_non_empty(request.goal, "goal")
        require_non_empty(request.channels, "channels")
        validate_user_request(request.product, request.audience, request.goal)
        self.logger.log("request_received", request)

        retrieved_context = self.knowledge_base.retrieve(request, limit=self.config.max_rag_chunks)
        self.logger.log("context_retrieved", retrieved_context)

        research = self.research_agent.run(request, retrieved_context)
        self.logger.log("research_completed", research)

        strategy_candidates = self.strategy_agent.generate_candidates(request, research)
        self.logger.log("strategy_candidates_completed", strategy_candidates)

        strategy = max(strategy_candidates, key=lambda candidate: candidate.score).strategy
        self.logger.log("strategy_completed", strategy)

        content = self.content_agent.run(request, research, strategy)
        self.logger.log("content_completed", content)

        creative_review = review_creative(
            research,
            strategy,
            content,
            iteration=1,
            threshold=self.config.review_threshold,
        )
        self.logger.log("creative_review_completed", creative_review)

        while not creative_review.passed and creative_review.iteration < self.config.max_revision_rounds:
            content = self.content_agent.revise(content, creative_review)
            self.logger.log("content_revised", content)
            creative_review = review_creative(
                research,
                strategy,
                content,
                iteration=creative_review.iteration + 1,
                threshold=self.config.review_threshold,
            )
            self.logger.log("creative_review_recompleted", creative_review)

        evaluation = evaluate_campaign(strategy, content, creative_review)
        self.logger.log("evaluation_completed", evaluation)

        package = CampaignPackage(
            request=request,
            retrieved_context=retrieved_context,
            research=research,
            strategy_candidates=strategy_candidates,
            strategy=strategy,
            content=content,
            creative_review=creative_review,
            evaluation=evaluation,
        )
        self.logger.log("campaign_completed", package)
        return package
