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
    chunk_id: str = ""
    line_start: int = 0
    line_end: int = 0
    retrieval_reason: str = ""


@dataclass(frozen=True)
class BrandFacts:
    value_proposition: str
    voice: list[str]
    avoid: list[str]
    customer_priorities: list[str]
    preferred_channels: list[str]
    content_style: list[str]
    citations: list[str]


@dataclass(frozen=True)
class ResearchBrief:
    brand_facts: BrandFacts
    audience_insights: list[str]
    competitors: list[str]
    pain_points: list[str]
    opportunities: list[str]
    assumptions: list[str]
    citations: list[str]


@dataclass(frozen=True)
class StrategyBrief:
    positioning: str
    messaging_pillars: list[str]
    channel_plan: list[str]
    funnel_steps: list[str]
    success_metrics: list[str]
    rejected_angles: list[str]
    risk_flags: list[str]
    hypothesis: str = ""


@dataclass(frozen=True)
class StrategyCandidate:
    name: str
    strategy: StrategyBrief
    score: int
    rationale: list[str]


@dataclass(frozen=True)
class ContentPackage:
    ad_variants: list[str]
    social_posts: list[dict[str, str]]
    email_drafts: list[dict[str, str]]
    landing_page_copy: dict[str, str]
    revision_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CreativeReview:
    passed: bool
    score: int
    issues: list[str]
    revision_brief: list[str]
    iteration: int = 1


@dataclass(frozen=True)
class EvaluationReport:
    score: int
    checks: dict[str, bool]
    recommendations: list[str]
    category_scores: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CampaignPackage:
    request: CampaignRequest
    retrieved_context: list[RetrievedContext]
    research: ResearchBrief
    strategy_candidates: list[StrategyCandidate]
    strategy: StrategyBrief
    content: ContentPackage
    creative_review: CreativeReview
    evaluation: EvaluationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "retrieved_context": self.retrieved_context,
            "research": self.research,
            "strategy_candidates": self.strategy_candidates,
            "strategy": self.strategy,
            "content": self.content,
            "creative_review": self.creative_review,
            "evaluation": self.evaluation,
        }
