from __future__ import annotations

import logging
from dataclasses import replace

from marketing_agents.brand_facts import extract_brand_facts
from marketing_agents.contracts import (
    CampaignRequest,
    ContentPackage,
    CreativeReview,
    ResearchBrief,
    RetrievedContext,
    StrategyBrief,
    StrategyCandidate,
    ExecutionContext,
    ABTestCell,
    RevisionAction,
)
from marketing_agents.goal_translator import translate_goal
from marketing_agents.llm import MarketingModel
from marketing_agents.validation import ContractValidationError, validate_contract

_log = logging.getLogger(__name__)


def flatten_text(value: object) -> str:
    """Recursively flatten any LLM-returned value into a single text string.

    Handles strings, lists (including nested), and dicts (values only).
    Falls back to str() for any other type so scoring never crashes.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for v in value.values())
    return str(value)


# ---------------------------------------------------------------------------
# Research Agent
# ---------------------------------------------------------------------------

class ResearchAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(self, request: CampaignRequest, context: list[RetrievedContext], exec_context: ExecutionContext = None) -> ResearchBrief:
        brand_facts = extract_brand_facts(context)
        
        # Persona Marketing (Phase 1)
        if request.target_personas:
            _log.info(f"[ResearchAgent] Injecting personas into research context: {request.target_personas}")
        
        brief = self.model.research(request, brand_facts)
        
        for attempt in range(3):
            # Always compute the customer-language goal translation here
            brief = replace(brief, translated_goal=translate_goal(request.goal))
            try:
                validate_contract(brief)
                return brief
            except ContractValidationError as e:
                if attempt == 2 or not hasattr(self.model, "_call_json"):
                    raise
                
                field = str(e).split(" must be")[0].strip()
                print(f"[ResearchAgent] repair retry {attempt + 1}/2 field={field}")
                
                repair_prompt = (
                    "The previous response violated schema.\n\n"
                    f"Problem:\n{e}\n\n"
                    f"Generate at least 3 realistic items for '{field}'.\n\n"
                    f"Audience:\n{request.audience}\n\n"
                    f"Goal:\n{request.goal}\n\n"
                    "Return valid JSON only, using the EXACT key:\n"
                    f'{{"{field}": [...]}}'
                )
                
                repaired_data = self.model._call_json(repair_prompt, {"field_to_repair": field})
                if field in repaired_data:
                    brief = replace(brief, **{field: repaired_data[field]})

        return brief


# ---------------------------------------------------------------------------
# Strategy Agent  — V7: 4 genuine archetypes + diversity penalty
# ---------------------------------------------------------------------------

class StrategyAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(self, request: CampaignRequest, research: ResearchBrief, exec_context: ExecutionContext = None) -> StrategyBrief:
        candidates = self.generate_candidates(request, research, exec_context)
        return max(candidates, key=lambda c: c.score).strategy

    def generate_candidates(
        self, request: CampaignRequest, research: ResearchBrief, exec_context: ExecutionContext = None
    ) -> list[StrategyCandidate]:
        base = self.model.strategy(request, research)

        priority = (
            research.brand_facts.customer_priorities[0]
            if research.brand_facts.customer_priorities
            else "saving time"
        )
        voice = ", ".join(research.brand_facts.voice[:2]) or request.tone
        channels = research.brand_facts.preferred_channels or request.channels
        avoid_summary = (
            ", ".join(research.brand_facts.avoid[:2])
            if research.brand_facts.avoid
            else "unsupported claims"
        )
        translated = research.translated_goal

        # ---- Archetype 1: Stress Reduction --------------------------------
        # Entry point: emotional pain, overwhelm, anxiety before action.
        stress_reduction = StrategyCandidate(
            name="stress-reduction",
            strategy=replace(
                base,
                positioning=(
                    f"{request.product} takes the pressure off {request.audience} "
                    f"by making {priority} feel manageable — not overwhelming."
                ),
                messaging_pillars=[
                    f"Name the stress: {priority} feels hard right now",
                    "Reduce the friction before the first step",
                    f"Speak calmly and directly — avoid pressure language like {avoid_summary}",
                ],
                hypothesis=(
                    f"When {request.audience} feel the emotional relief of {priority} "
                    f"being easier, they will {translated} with less hesitation."
                ),
            ),
            score=0,
            rationale=["Leads with emotional pain relief — lowers the barrier to trying."],
        )

        # ---- Archetype 2: Productivity Gain --------------------------------
        # Entry point: measurable, rational efficiency gains.
        productivity_gain = StrategyCandidate(
            name="productivity-gain",
            strategy=replace(
                base,
                positioning=(
                    f"{request.product} helps {request.audience} "
                    f"accomplish {priority} faster, with less wasted effort."
                ),
                messaging_pillars=[
                    f"Show the concrete time or effort saved on {priority}",
                    "Lead with output, not process — what does the audience produce?",
                    f"Keep tone {voice}: practical evidence beats big claims",
                ],
                hypothesis=(
                    f"Demonstrating a tangible, specific gain in {priority} "
                    f"gives {request.audience} a rational reason to {translated}."
                ),
            ),
            score=0,
            rationale=["Leads with measurable gain — appeals to rational decision-makers."],
        )

        # ---- Archetype 3: Habit Building -----------------------------------
        # Entry point: identity change and long-term consistency.
        habit_building = StrategyCandidate(
            name="habit-building",
            strategy=replace(
                base,
                positioning=(
                    f"{request.product} helps {request.audience} build {priority} "
                    f"into a consistent habit — one small step at a time."
                ),
                messaging_pillars=[
                    f"Frame {priority} as a habit, not a one-time effort",
                    "Use identity language: become the person who is consistent",
                    "Show how small, repeated actions compound into real change",
                ],
                hypothesis=(
                    f"Identity-based messaging ('become the {request.audience} who...')"
                    f" drives higher long-term retention after {request.audience} {translated}."
                ),
            ),
            score=0,
            rationale=["Leads with identity and habit — drives retention beyond first action."],
        )

        # ---- Archetype 4: Social Proof ------------------------------------
        # Entry point: peer validation, community, belonging.
        social_proof = StrategyCandidate(
            name="social-proof",
            strategy=replace(
                base,
                positioning=(
                    f"Join {request.audience} who already make {priority} work "
                    f"with {request.product}."
                ),
                messaging_pillars=[
                    f"Lead with community: others like you are already doing this",
                    f"Show peer success on {priority} — specific, not vague",
                    "Use belonging language — nobody wants to be the last to figure this out",
                ],
                hypothesis=(
                    f"Social proof reduces scepticism: when {request.audience} see "
                    f"peers succeeding with {priority}, they {translated} faster."
                ),
            ),
            score=0,
            rationale=["Leads with community validation — activates belonging and reduces hesitation."],
        )

        raw_candidates = [stress_reduction, productivity_gain, habit_building, social_proof]

        # Score all candidates individually
        scored = [
            replace(c, score=self._score_strategy(c.strategy, research))
            for c in raw_candidates
        ]

        # Apply diversity penalty: candidates that converge on similar pillars
        # get penalised to reward genuinely different thinking.
        final = self._apply_diversity_penalty(scored)
        return final

    def _score_strategy(self, strategy: StrategyBrief, research: ResearchBrief) -> int:
        # Detect unexpected shapes from local LLMs and log once (no spam).
        _mixed = [
            f for f in (strategy.messaging_pillars + strategy.risk_flags)
            if not isinstance(f, str)
        ]
        if _mixed:
            _log.debug(
                "[StrategyAgent] normalizing LLM structure for scoring: %s",
                [type(x).__name__ for x in _mixed],
            )

        text = flatten_text([
            strategy.positioning,
            strategy.hypothesis,
            strategy.messaging_pillars,
            strategy.channel_plan,
            strategy.risk_flags,
        ]).lower()
        score = 60
        score += sum(8 for p in research.brand_facts.customer_priorities if p.lower() in text)
        score += sum(5 for ch in research.brand_facts.preferred_channels if ch.lower() in text)
        score += sum(4 for v in research.brand_facts.voice if v.lower() in text)
        score += 10 if strategy.risk_flags else 0
        return min(score, 100)

    def _apply_diversity_penalty(
        self, candidates: list[StrategyCandidate]
    ) -> list[StrategyCandidate]:
        """Penalise candidates whose messaging pillars overlap > 60% with another candidate.

        This enforces genuine strategic differentiation — if two candidates say
        essentially the same thing in different words, the lower-scoring one is
        penalised so the pipeline is incentivised to select a meaningfully different angle.
        """
        result = list(candidates)
        for i, candidate in enumerate(candidates):
            own_words = {
                w
                for p in candidate.strategy.messaging_pillars
                for w in flatten_text(p).lower().split()
                if len(w) > 4
            }
            for j, other in enumerate(candidates):
                if i == j:
                    continue
                other_words = {
                    w
                    for p in other.strategy.messaging_pillars
                    for w in flatten_text(p).lower().split()
                    if len(w) > 4
                }
                union = own_words | other_words
                if not union:
                    continue
                overlap = len(own_words & other_words) / len(union)
                if overlap > 0.60:
                    # Penalise the lower-scoring candidate of the pair
                    if candidate.score <= other.score:
                        penalised = replace(result[i], score=max(0, result[i].score - 15))
                        result[i] = penalised
        return result


# ---------------------------------------------------------------------------
# Content Agent
# ---------------------------------------------------------------------------

class ContentAgent:
    def __init__(self, model: MarketingModel) -> None:
        self.model = model

    def run(
        self,
        request: CampaignRequest,
        research: ResearchBrief,
        strategy: StrategyBrief,
        exec_context: ExecutionContext = None,
    ) -> ContentPackage:
        raw = self.model.content(request, research, strategy)
        
        raw_variants = raw.get("ad_variants", [])
        ab_variants = []
        for v in raw_variants:
            if isinstance(v, dict):
                ab_variants.append(ABTestCell(control=v.get("control", ""), variant=v.get("variant", "")))
            elif isinstance(v, ABTestCell):
                ab_variants.append(v)
            else:
                ab_variants.append(ABTestCell(control=str(v), variant=""))
                
        package = ContentPackage(
            ad_variants=ab_variants,
            social_posts=list(raw.get("social_posts", [])),
            email_drafts=list(raw.get("email_drafts", [])),
            landing_page_copy=dict(raw.get("landing_page_copy", {})),
            revision_notes=list(raw.get("revision_notes", ["Initial draft completed."])),
        )
        package = self._self_critique(package, strategy)
        validate_contract(package)
        return package

    def _self_critique(self, package: ContentPackage, strategy: StrategyBrief) -> ContentPackage:
        issues = []
        if not package.ad_variants:
            issues.append("No ad variants generated.")
        else:
            # Check if AB Testing was properly formatted
            if any(not v.variant for v in package.ad_variants):
                issues.append("Missing explicit variant testing angles.")
        if issues:
            return replace(package, revision_notes=package.revision_notes + ["Self-Critique finding: " + "; ".join(issues)])
        return package

    def revise(self, package: ContentPackage, review: CreativeReview, exec_context: ExecutionContext = None) -> ContentPackage:
        if review.passed:
            return package

        revised_ads = list(package.ad_variants)
        if review.revision_brief:
            note = review.revision_brief[0]
            if isinstance(note, RevisionAction):
                # Apply granular target action
                if "ad_variant" in note.target_asset and revised_ads:
                    old_cell = revised_ads[0]
                    revised_ads[0] = replace(old_cell, control=f"{old_cell.control} [Revised: {note.action}]")
            else:
                if revised_ads:
                    old_cell = revised_ads[0]
                    revised_ads[0] = replace(old_cell, control=f"{old_cell.control} [Revised: {note[:80]}]")

        return replace(
            package,
            ad_variants=revised_ads,
            revision_notes=package.revision_notes + review.revision_brief,
        )
