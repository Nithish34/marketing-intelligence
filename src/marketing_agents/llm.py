from __future__ import annotations

from abc import ABC, abstractmethod

from marketing_agents.contracts import CampaignRequest, ResearchBrief, StrategyBrief


class MarketingModel(ABC):
    @abstractmethod
    def research(self, request: CampaignRequest, context_text: str) -> ResearchBrief:
        raise NotImplementedError

    @abstractmethod
    def strategy(self, request: CampaignRequest, research: ResearchBrief) -> StrategyBrief:
        raise NotImplementedError

    @abstractmethod
    def content(self, request: CampaignRequest, strategy: StrategyBrief) -> dict[str, object]:
        raise NotImplementedError


class RuleBasedMarketingModel(MarketingModel):
    """Deterministic local model for v1 development and tests."""

    def research(self, request: CampaignRequest, context_text: str) -> ResearchBrief:
        product = request.product
        audience = request.audience
        context_hint = "brand context" if context_text else "the product brief"
        return ResearchBrief(
            audience_insights=[
                f"{audience} need fast proof that {product} can solve a concrete business problem.",
                f"They will compare setup effort, credibility, and time-to-value before responding.",
                f"Messaging should connect the campaign goal, '{request.goal}', to a measurable next step.",
            ],
            competitors=[
                "manual spreadsheets and ad-hoc workflows",
                "generic all-in-one tools",
                "larger incumbent platforms with heavier setup",
            ],
            pain_points=[
                "unclear ROI from current marketing activity",
                "too much time spent turning strategy into usable assets",
                "inconsistent messaging across channels",
            ],
            opportunities=[
                f"Position {product} as a practical way to move from idea to campaign faster.",
                f"Use {context_hint} to make claims specific, credible, and reusable.",
                "Create channel-specific variants while keeping one clear campaign promise.",
            ],
            citations=["knowledge_base" if context_text else "campaign_request"],
        )

    def strategy(self, request: CampaignRequest, research: ResearchBrief) -> StrategyBrief:
        return StrategyBrief(
            positioning=(
                f"{request.product} helps {request.audience} achieve {request.goal} with a "
                "clearer, faster marketing workflow."
            ),
            messaging_pillars=[
                "Speed from brief to campaign",
                "Consistent messaging across every channel",
                "Practical outputs that teams can review, edit, and launch",
            ],
            channel_plan=[
                f"{channel}: adapt the core promise for {request.audience}"
                for channel in request.channels
            ],
            funnel_steps=[
                "Awareness: name the urgent pain",
                "Consideration: show the workflow improvement",
                "Conversion: invite a low-friction next step",
            ],
            success_metrics=[
                "conversion rate",
                "cost per qualified lead",
                "demo or signup rate",
                "asset approval time",
            ],
        )

    def content(self, request: CampaignRequest, strategy: StrategyBrief) -> dict[str, object]:
        promise = strategy.messaging_pillars[0].lower()
        return {
            "ad_variants": [
                f"Turn scattered ideas into ready-to-review campaigns. {request.product} gives {request.audience} {promise}.",
                f"Still building campaigns one asset at a time? Use {request.product} to move faster and keep every message aligned.",
                f"Launch better campaigns without the usual blank-page drag. Built for {request.audience}.",
                f"Your next campaign can be clearer before it gets bigger. Start with {request.product}.",
                f"From strategy to ads, emails, and landing page copy: make {request.goal} easier to execute.",
            ],
            "social_posts": [
                f"{request.audience} do not need more random content. They need one sharp campaign idea turned into assets that match.",
                f"A strong campaign starts with a clear promise: {strategy.positioning}",
                f"Marketing moves faster when research, strategy, and content are part of one workflow.",
                f"Before writing another ad, define the pain, proof, and next step. Then create variants.",
                f"{request.product} helps teams make campaign work easier to review and easier to launch.",
            ],
            "email_drafts": [
                {
                    "subject": f"A faster path to {request.goal}",
                    "body": (
                        f"Hi there,\n\nIf your team is trying to {request.goal}, {request.product} can help turn "
                        "the brief into campaign-ready assets without losing the core message.\n\n"
                        "Worth a quick look this week?"
                    ),
                },
                {
                    "subject": "Less blank page, more campaign momentum",
                    "body": (
                        f"Hi there,\n\n{request.audience} often have the strategy in pieces: notes, ideas, old copy, "
                        f"and channel plans. {request.product} brings those pieces into one usable campaign package.\n\n"
                        "Happy to send a sample."
                    ),
                },
                {
                    "subject": "Make every channel say the same important thing",
                    "body": (
                        f"Hi there,\n\nWhen the goal is {request.goal}, inconsistent messaging slows everything down. "
                        f"{request.product} helps create aligned ads, posts, emails, and landing page copy from one strategy.\n\n"
                        "Can I share what that looks like?"
                    ),
                },
            ],
            "landing_page_copy": {
                "headline": f"Build campaigns that help {request.audience} {request.goal}",
                "subheadline": (
                    f"{request.product} turns research and strategy into ads, social posts, emails, "
                    "and landing page copy your team can refine and launch."
                ),
                "primary_cta": "Generate my campaign",
                "secondary_cta": "See sample output",
            },
        }

