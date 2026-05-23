from __future__ import annotations

from marketing_agents.contracts import CampaignRequest, ContentPackage, ResearchBrief, RetrievedContext, StrategyBrief
from marketing_agents.llm import MarketingModel
from marketing_agents.validation import validate_contract


class ResearchAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(self, request: CampaignRequest, context: list[RetrievedContext]) -> ResearchBrief:
        context_text = "\n\n".join(chunk.text for chunk in context)
        brief = self.model.research(request, context_text)
        validate_contract(brief)
        return brief


class StrategyAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(self, request: CampaignRequest, research: ResearchBrief) -> StrategyBrief:
        brief = self.model.strategy(request, research)
        validate_contract(brief)
        return brief


class ContentAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(self, request: CampaignRequest, strategy: StrategyBrief) -> ContentPackage:
        raw = self.model.content(request, strategy)
        package = ContentPackage(
            ad_variants=list(raw["ad_variants"]),
            social_posts=list(raw["social_posts"]),
            email_drafts=list(raw["email_drafts"]),
            landing_page_copy=dict(raw["landing_page_copy"]),
        )
        validate_contract(package)
        return package

