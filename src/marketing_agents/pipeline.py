from __future__ import annotations

from pathlib import Path

from marketing_agents.agents import ContentAgent, ResearchAgent, StrategyAgent
from marketing_agents.contracts import CampaignPackage, CampaignRequest
from marketing_agents.evaluation import evaluate_campaign
from marketing_agents.llm import MarketingModel, RuleBasedMarketingModel
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
    ) -> None:
        self.knowledge_base = knowledge_base or LocalKnowledgeBase()
        self.model = model or RuleBasedMarketingModel()
        self.logger = logger or JsonlRunLogger()
        self.research_agent = ResearchAgent(self.model)
        self.strategy_agent = StrategyAgent(self.model)
        self.content_agent = ContentAgent(self.model)

    @classmethod
    def from_paths(cls, knowledge_base_dir: Path | str = "knowledge_base", log_path: Path | str = "runs/marketing_runs.jsonl") -> "MarketingPipeline":
        return cls(knowledge_base=LocalKnowledgeBase(knowledge_base_dir), logger=JsonlRunLogger(log_path))

    def run(self, request: CampaignRequest) -> CampaignPackage:
        require_non_empty(request.product, "product")
        require_non_empty(request.audience, "audience")
        require_non_empty(request.goal, "goal")
        require_non_empty(request.channels, "channels")
        validate_user_request(request.product, request.audience, request.goal)
        self.logger.log("request_received", request)

        retrieved_context = self.knowledge_base.retrieve(request)
        self.logger.log("context_retrieved", retrieved_context)

        research = self.research_agent.run(request, retrieved_context)
        self.logger.log("research_completed", research)

        strategy = self.strategy_agent.run(request, research)
        self.logger.log("strategy_completed", strategy)

        content = self.content_agent.run(request, strategy)
        self.logger.log("content_completed", content)

        evaluation = evaluate_campaign(strategy, content)
        self.logger.log("evaluation_completed", evaluation)

        package = CampaignPackage(
            request=request,
            retrieved_context=retrieved_context,
            research=research,
            strategy=strategy,
            content=content,
            evaluation=evaluation,
        )
        self.logger.log("campaign_completed", package)
        return package
