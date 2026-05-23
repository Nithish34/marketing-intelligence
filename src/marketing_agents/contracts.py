from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CampaignRequest:
    product: str
    audience: str
    goal: str
    tone: str = "clear, useful, and credible"
    channels: list[str] = field(default_factory=lambda: ["paid social", "email", "landing page"])
    constraints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievedContext:
    source: str
    text: str
    score: int


@dataclass(frozen=True)
class ResearchBrief:
    audience_insights: list[str]
    competitors: list[str]
    pain_points: list[str]
    opportunities: list[str]
    citations: list[str]


@dataclass(frozen=True)
class StrategyBrief:
    positioning: str
    messaging_pillars: list[str]
    channel_plan: list[str]
    funnel_steps: list[str]
    success_metrics: list[str]


@dataclass(frozen=True)
class ContentPackage:
    ad_variants: list[str]
    social_posts: list[str]
    email_drafts: list[dict[str, str]]
    landing_page_copy: dict[str, str]


@dataclass(frozen=True)
class EvaluationReport:
    score: int
    checks: dict[str, bool]
    recommendations: list[str]


@dataclass(frozen=True)
class CampaignPackage:
    request: CampaignRequest
    retrieved_context: list[RetrievedContext]
    research: ResearchBrief
    strategy: StrategyBrief
    content: ContentPackage
    evaluation: EvaluationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "retrieved_context": self.retrieved_context,
            "research": self.research,
            "strategy": self.strategy,
            "content": self.content,
            "evaluation": self.evaluation,
        }

