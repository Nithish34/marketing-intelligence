from __future__ import annotations

from dataclasses import replace

from marketing_agents.brand_facts import extract_brand_facts
from marketing_agents.contracts import CampaignRequest, ContentPackage, CreativeReview, ResearchBrief, RetrievedContext, StrategyBrief, StrategyCandidate
from marketing_agents.llm import MarketingModel
from marketing_agents.validation import validate_contract


class ResearchAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(self, request: CampaignRequest, context: list[RetrievedContext]) -> ResearchBrief:
        brand_facts = extract_brand_facts(context)
        brief = self.model.research(request, brand_facts)
        validate_contract(brief)
        return brief


class StrategyAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(self, request: CampaignRequest, research: ResearchBrief) -> StrategyBrief:
        candidates = self.generate_candidates(request, research)
        return max(candidates, key=lambda candidate: candidate.score).strategy

    def generate_candidates(self, request: CampaignRequest, research: ResearchBrief) -> list[StrategyCandidate]:
        base = self.model.strategy(request, research)
        priority = research.brand_facts.customer_priorities[0] if research.brand_facts.customer_priorities else request.goal
        voice = ", ".join(research.brand_facts.voice[:2]) or request.tone
        channels = research.brand_facts.preferred_channels or request.channels

        candidates = [
            StrategyCandidate(
                name="priority-led",
                strategy=base,
                score=self._score_strategy(base, research),
                rationale=["Directly anchors the campaign on the strongest retrieved customer priority."],
            ),
            StrategyCandidate(
                name="channel-led",
                strategy=replace(
                    base,
                    positioning=f"{request.product} meets {request.audience} on {', '.join(channels[:3])} with practical steps toward {request.goal}.",
                    messaging_pillars=[
                        f"Make {priority} visible in each channel",
                        "Adapt the same promise without copy-paste messaging",
                        f"Keep the tone {voice}",
                    ],
                    hypothesis="Channel-native content will improve engagement because each asset matches the user's context.",
                ),
                score=0,
                rationale=["Emphasizes native execution for the retrieved preferred channels."],
            ),
            StrategyCandidate(
                name="risk-reduction",
                strategy=replace(
                    base,
                    positioning=f"{request.product} helps {request.audience} move toward {request.goal} without overpromising outcomes.",
                    messaging_pillars=[
                        "Be useful before asking for action",
                        f"Show how {priority} improves with small steps",
                        "Avoid pressure, hype, and unsupported claims",
                    ],
                    hypothesis="Trust-first messaging will reduce skepticism and make signup feel lower risk.",
                ),
                score=0,
                rationale=["Prioritizes avoid rules, credibility, and safer claims."],
            ),
        ]

        return [
            replace(candidate, score=self._score_strategy(candidate.strategy, research))
            for candidate in candidates
        ]

    def _score_strategy(self, strategy: StrategyBrief, research: ResearchBrief) -> int:
        text = " ".join(
            [strategy.positioning, strategy.hypothesis]
            + strategy.messaging_pillars
            + strategy.channel_plan
            + strategy.risk_flags
        ).lower()
        score = 60
        score += sum(8 for priority in research.brand_facts.customer_priorities if priority.lower() in text)
        score += sum(5 for channel in research.brand_facts.preferred_channels if channel.lower() in text)
        score += sum(4 for voice in research.brand_facts.voice if voice.lower() in text)
        score += 10 if strategy.risk_flags else 0
        return min(score, 100)


class ContentAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(self, request: CampaignRequest, research: ResearchBrief, strategy: StrategyBrief) -> ContentPackage:
        raw = self.model.content(request, research, strategy)
        package = ContentPackage(
            ad_variants=list(raw["ad_variants"]),
            social_posts=list(raw["social_posts"]),
            email_drafts=list(raw["email_drafts"]),
            landing_page_copy=dict(raw["landing_page_copy"]),
            revision_notes=list(raw.get("revision_notes", ["Initial draft completed."])),
        )
        validate_contract(package)
        return package

    def revise(self, package: ContentPackage, review: CreativeReview) -> ContentPackage:
        if review.passed:
            return package

        revised_ads = list(package.ad_variants)
        if review.revision_brief:
            revised_ads[0] = f"{revised_ads[0]} Clear, grounded next step included for review alignment."

        return replace(
            package,
            ad_variants=revised_ads,
            revision_notes=package.revision_notes + review.revision_brief,
        )
