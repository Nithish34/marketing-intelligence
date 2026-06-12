from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union


@dataclass(frozen=True)
class CampaignRequest:
    product: str
    audience: str
    goal: str
    tone: str = "clear, useful, and credible"
    channels: list[str] = field(default_factory=lambda: ["paid social", "email", "landing page"])
    constraints: list[str] = field(default_factory=list)
    target_personas: list[str] = field(default_factory=list)

@dataclass
class ExecutionContext:
    current_stage: str = "init"
    active_hypotheses: list[str] = field(default_factory=list)
    previous_errors: list[str] = field(default_factory=list)
    memory_bank_hits: int = 0


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
    # Customer-facing version of campaign goal — set by ResearchAgent via goal_translator,
    # not by the model directly. Models set this to request.goal as a placeholder.
    translated_goal: str = "take the next step"


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
    ab_test_variable: str = "Emotional vs Rational"


@dataclass(frozen=True)
class StrategyCandidate:
    name: str
    strategy: StrategyBrief
    score: int
    rationale: list[str]


@dataclass(frozen=True)
class CategoryScores:
    """CMO-driven creative review scores. Max total = 100.

    Weights reflect the cost of fixing each failure:
      - single_minded_message (25): structural — hardest to fix
      - audience_truth (20): strategic — requires rethinking voice
      - brand_integrity (20): strategic — avoid rules are non-negotiable
      - conversion_logic (15): tactical — CTA edits are fast
      - claim_honesty (15): ethical — unsupported claims floor the category
      - channel_nativeness (5): cosmetic — easiest to fix in revision
    """
    single_minded_message: int  # 0-25: One clear promise consistent across all assets
    audience_truth: int         # 0-20: Speaks the customer's language, not business jargon
    brand_integrity: int        # 0-20: Sounds like this specific brand; avoid rules respected
    conversion_logic: int       # 0-15: Clear, proportionate, low-friction CTA path
    claim_honesty: int          # 0-15: Every claim grounded, specific, and believable
    channel_nativeness: int     # 0-5:  Each asset fits its channel's native grammar


@dataclass(frozen=True)
class ABTestCell:
    control: str
    variant: str

@dataclass(frozen=True)
class RevisionAction:
    target_asset: str
    action: str
    reason: str

@dataclass(frozen=True)
class ContentPackage:
    ad_variants: list[ABTestCell]
    social_posts: list[dict[str, str]]
    email_drafts: list[dict[str, str]]
    landing_page_copy: dict[str, str]
    revision_notes: list[Union[str, RevisionAction]] = field(default_factory=list)


@dataclass(frozen=True)
class CreativeReview:
    passed: bool
    score: int                        # Sum of all category_scores (max 100)
    category_scores: CategoryScores   # Granular CMO-driven breakdown
    issues: list[str]
    revision_brief: list[Union[str, RevisionAction]]
    iteration: int = 1


@dataclass(frozen=True)
class EvaluationReport:
    score: int
    checks: dict[str, bool]
    recommendations: list[str]
    category_scores: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class RunDiagnostics:
    """Per-run quality signals logged for observability and debugging.

    These signals help diagnose weak runs — for example a low
    retrieval_quality score tells you the KB had nothing relevant,
    while low strategy_diversity tells you the candidates converged.
    """
    retrieval_quality: int      # 0-100: Best RAG chunk score, normalised
    strategy_diversity: int     # 0-100: Lexical uniqueness across strategy candidates
    content_originality: int    # 0-100: Variance across ad variant openings
    review_confidence: int      # 0-100: How far above threshold the review scored
    goal_translation_used: bool # True when customer-language translation was applied
    semantic_boost_applied: bool = False # V7: True if semantic search boosted a chunk


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
    diagnostics: RunDiagnostics

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
            "diagnostics": self.diagnostics,
        }
