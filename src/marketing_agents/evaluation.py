from __future__ import annotations

from marketing_agents.contracts import (
    ABTestCell,
    CampaignPackage,
    CategoryScores,
    ContentPackage,
    CreativeReview,
    EvaluationReport,
    ResearchBrief,
    StrategyBrief,
)
from marketing_agents.agents import flatten_text

# ---------------------------------------------------------------------------
# Lexical constants used by the CMO-driven reviewer
# ---------------------------------------------------------------------------

# CTAs that are too vague to drive action
WEAK_CTA_WORDS: frozenset[str] = frozenset({
    "learn more", "find out", "discover", "click here", "read more",
    "see more", "explore", "check it out", "visit us", "contact us",
    "get in touch", "see details", "view more",
})

# Phrases that make claims that cannot be verified
SUPERLATIVE_PHRASES: frozenset[str] = frozenset({
    "guaranteed", "always works", "never fails", "100% proven",
    "best in class", "world-class", "state of the art", "cutting-edge",
    "number one", "#1 rated", "scientifically proven", "clinically proven",
    "fastest", "cheapest", "most powerful",
})

# Hard-fail guarantees: any single match floors claim_honesty to 0
HARD_GUARANTEE_PHRASES: frozenset[str] = frozenset({
    "guaranteed results", "we guarantee", "money-back guarantee",
    "always works", "never fails", "100% success",
})

# Generic marketing buzzwords that make copy interchangeable with competitors
GENERIC_BUZZWORDS: frozenset[str] = frozenset({
    "innovative", "revolutionary", "game-changing", "disruptive",
    "transformative", "seamless experience", "robust solution",
    "next-generation", "best-in-class", "leverage", "synergy",
    "empower", "holistic", "paradigm shift", "state-of-the-art",
    "cutting-edge", "unprecedented", "groundbreaking", "world-class",
    "premier", "optimal", "maximize", "streamline", "unleash",
})


def flatten_ad_variants(ad_variants: list[object]) -> str:
    """Flatten current ABTestCell ads plus legacy string/dict ad shapes."""
    parts: list[str] = []
    for ad in ad_variants:
        if isinstance(ad, ABTestCell):
            parts.extend([ad.control, ad.variant])
        elif isinstance(ad, dict):
            parts.extend(str(value) for value in ad.values())
        else:
            parts.append(flatten_text(ad))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Category 1 — Single-Minded Message  (0–25 pts)
# ---------------------------------------------------------------------------

def _score_single_minded_message(
    content: ContentPackage,
    strategy: StrategyBrief,
) -> tuple[int, list[str], list[str]]:
    """One clear promise, consistent across all assets."""
    issues: list[str] = []
    revision_brief: list[str] = []
    score = 0

    combined_ads = flatten_ad_variants(content.ad_variants).lower()

    # Check 1: Messaging pillars visible in ad copy (0–15)
    pillar_words = {
        w for p in strategy.messaging_pillars
        for w in p.lower().split()
        if len(w) > 4
    }
    pillar_hits = sum(1 for w in pillar_words if w in combined_ads)
    pillar_ratio = pillar_hits / max(len(pillar_words), 1)

    if pillar_ratio >= 0.5:
        score += 15
    elif pillar_ratio >= 0.3:
        score += 8
        issues.append("Messaging pillars only weakly reflected across ad variants.")
        revision_brief.append("Anchor at least 3 ad variants on the primary messaging pillar.")
    else:
        score += 2
        issues.append("Ad variants do not visibly connect to the strategy messaging pillars.")
        revision_brief.append("Rewrite ad variants to lead with the primary messaging pillar.")

    # Check 2: Variant uniqueness — penalise copy-paste openings (0–10)
    openings = [
        flatten_text(ad.control if isinstance(ad, ABTestCell) else ad).split()[0].lower()
        for ad in content.ad_variants
        if flatten_text(ad.control if isinstance(ad, ABTestCell) else ad).split()
    ]
    unique_openings = len(set(openings))

    if unique_openings >= 4:
        score += 10
    elif unique_openings >= 2:
        score += 5
        issues.append("Several ad variants open with the same word — may feel repetitive.")
    else:
        issues.append("Ad variants start identically; audience will tune them out.")
        revision_brief.append("Vary the opening hook across all 5 ad variants.")

    return min(score, 25), issues, revision_brief


# ---------------------------------------------------------------------------
# Category 2 — Audience Truth  (0–20 pts)
# ---------------------------------------------------------------------------

def _score_audience_truth(
    research: ResearchBrief,
    content: ContentPackage,
    original_goal: str,
) -> tuple[int, list[str], list[str]]:
    """Speaks the customer's language — not the business's language."""
    issues: list[str] = []
    revision_brief: list[str] = []
    score = 0

    combined = (
        flatten_ad_variants(content.ad_variants)
        + " " + flatten_text(content.social_posts)
        + " " + flatten_text(content.email_drafts)
        + " " + flatten_text(content.landing_page_copy)
    ).lower()

    # Check 1: Customer priorities reflected in copy (0–10)
    if research.brand_facts.customer_priorities:
        priority_hits = sum(
            1 for p in research.brand_facts.customer_priorities
            if p.lower() in combined
        )
        if priority_hits >= 2:
            score += 10
        elif priority_hits == 1:
            score += 5
            issues.append("Only one customer priority appears in the copy.")
            revision_brief.append(
                f"Weave at least two priorities into the copy: "
                f"{', '.join(research.brand_facts.customer_priorities[:3])}."
            )
        else:
            issues.append("Customer priorities from the brand brief are absent from the copy.")
            revision_brief.append(
                f"Lead with the top customer priority: "
                f"'{research.brand_facts.customer_priorities[0]}'."
            )
    else:
        score += 5  # Neutral — no priorities retrieved to check against

    # Check 2: Business goal language should NOT appear verbatim in customer copy (0–6)
    goal_leak = original_goal.lower() in combined
    if not goal_leak:
        score += 6
    else:
        issues.append(
            f"Business goal language leaked into customer copy: '{original_goal}'. "
            "Customers never talk this way about themselves."
        )
        revision_brief.append(
            "Replace the raw campaign goal with customer-language: what does the "
            "audience get, feel, or become — not what the business measures."
        )

    # Check 3: Content style reflected (0–4)
    if research.brand_facts.content_style:
        style_hits = sum(
            1 for s in research.brand_facts.content_style
            if s.lower() in combined
        )
        if style_hits >= 1:
            score += 4
        else:
            score += 1
            issues.append("Retrieved content style is not reflected in the copy.")
            revision_brief.append(
                f"Make the tone more '{research.brand_facts.content_style[0]}'."
            )
    else:
        score += 4  # Neutral — no style retrieved

    return min(score, 20), issues, revision_brief


# ---------------------------------------------------------------------------
# Category 3 — Brand Integrity  (0–20 pts)
# ---------------------------------------------------------------------------

def _score_brand_integrity(
    research: ResearchBrief,
    content: ContentPackage,
) -> tuple[int, list[str], list[str]]:
    """Sounds like this specific brand — not a generic competitor."""
    issues: list[str] = []
    revision_brief: list[str] = []

    combined = (
        flatten_ad_variants(content.ad_variants)
        + " " + flatten_text(content.social_posts)
        + " " + flatten_text(content.email_drafts)
        + " " + flatten_text(content.landing_page_copy)
    ).lower()

    # Check 1: Avoid rules — hard deduction -7 per violation, floor 0 (0–14 range)
    avoid_violations = [
        rule for rule in research.brand_facts.avoid
        if rule.lower() in combined
    ]
    base = 14
    violation_penalty = len(avoid_violations) * 7
    avoid_score = max(0, base - violation_penalty)

    for rule in avoid_violations:
        issues.append(f"Avoid-rule violated: '{rule}'.")
        revision_brief.append(f"Remove or replace language related to '{rule}'.")

    # Check 2: Voice attributes present in copy (0–4)
    voice_score = 0
    if research.brand_facts.voice:
        voice_hits = sum(1 for v in research.brand_facts.voice if v.lower() in combined)
        voice_score = min(4, voice_hits * 2)
        if voice_hits == 0:
            issues.append("Brand voice attributes are not audible in the copy.")
            revision_brief.append(
                f"Write in a '{', '.join(research.brand_facts.voice[:2])}' voice throughout."
            )
    else:
        voice_score = 2  # Neutral

    # Check 3: Generic buzzwords make the brand interchangeable (-2 per hit, min 0) (0–2)
    buzzword_hits = sum(1 for b in GENERIC_BUZZWORDS if b in combined)
    
    # V7 Anti-Generic Engine: Structural check for LLM sameness ("Imagine a world...", "Are you tired of...")
    cliche_rhythms = ["imagine a world", "are you tired of", "look no further", "in today's fast-paced"]
    cliche_hits = sum(1 for c in cliche_rhythms if c in combined)
    
    total_generic_hits = buzzword_hits + (cliche_hits * 2)
    buzzword_score = max(0, 2 - total_generic_hits)
    
    if total_generic_hits > 0:
        issues.append(
            f"Generic marketing language detected ({total_generic_hits} instance(s)). "
            "A competitor could paste their name in and send this."
        )
        revision_brief.append("Replace buzzwords with specific, earned claims about this product.")

    score = avoid_score + voice_score + buzzword_score
    return min(score, 20), issues, revision_brief


# ---------------------------------------------------------------------------
# Category 4 — Conversion Logic  (0–15 pts)
# ---------------------------------------------------------------------------

def _score_conversion_logic(
    strategy: StrategyBrief,
    content: ContentPackage,
) -> tuple[int, list[str], list[str]]:
    """The path from seeing → doing is clear, proportionate, and low-friction."""
    issues: list[str] = []
    revision_brief: list[str] = []
    score = 0

    primary_cta = flatten_text(content.landing_page_copy.get("primary_cta", "")).lower() if isinstance(content.landing_page_copy, dict) else ""

    # Check 1: Primary CTA specificity (0–10)
    is_weak_cta = any(weak in primary_cta for weak in WEAK_CTA_WORDS)
    if not primary_cta:
        issues.append("No primary CTA found on the landing page.")
        revision_brief.append("Add a specific, action-oriented primary CTA to the landing page.")
    elif is_weak_cta:
        score += 4
        issues.append(f"Primary CTA is too vague: '{content.landing_page_copy.get('primary_cta', '')}'. "
                       "Vague CTAs reduce conversion.")
        revision_brief.append(
            "Replace the CTA with something specific to the product and audience — "
            "e.g. 'Create my study plan', 'Book a 15-min walkthrough', 'Get my free trial'."
        )
    else:
        score += 10  # Specific, action-oriented CTA

    # Check 2: Email CTA presence (0–3)
    emails_with_cta = sum(
        1 for draft in content.email_drafts
        if any(
            action in flatten_text(draft).lower()
            for action in ("reply", "click", "book", "sign", "try", "get", "join", "start", "create")
        )
    )
    if emails_with_cta >= 2:
        score += 3
    elif emails_with_cta == 1:
        score += 1
        issues.append("Most email drafts lack a clear next-step action.")
        revision_brief.append("End each email with one specific, low-friction action.")
    else:
        issues.append("Email drafts have no clear call to action.")
        revision_brief.append("Add a specific reply or click action to each email.")

    # Check 3: Funnel coherence (strategy defines steps) (0–2)
    if strategy.funnel_steps:
        score += 2

    return min(score, 15), issues, revision_brief


# ---------------------------------------------------------------------------
# Category 5 — Claim Honesty  (0–15 pts)
# ---------------------------------------------------------------------------

def _score_claim_honesty(
    research: ResearchBrief,
    content: ContentPackage,
) -> tuple[int, list[str], list[str]]:
    """Every claim is grounded, specific, and earnable."""
    issues: list[str] = []
    revision_brief: list[str] = []

    combined = (
        flatten_ad_variants(content.ad_variants) + " " + flatten_text(content.landing_page_copy)
    ).lower()

    # Hard floor check: unsupported guarantees floor this category to 0
    hard_violations = [phrase for phrase in HARD_GUARANTEE_PHRASES if phrase in combined]
    if hard_violations:
        issues.append(
            f"Unsupported guarantee detected: '{hard_violations[0]}'. "
            "This floors claim honesty to 0 — no partial credit."
        )
        revision_brief.append(
            "Remove all result guarantees. Replace with specific, earned claims "
            "grounded in retrieved brand context or the campaign request."
        )
        return 0, issues, revision_brief

    # Check 1: Superlative / exaggerated language (0–8)
    superlative_hits = sum(1 for phrase in SUPERLATIVE_PHRASES if phrase in combined)
    if superlative_hits == 0:
        score = 8
    elif superlative_hits == 1:
        score = 4
        issues.append("One superlative or exaggerated claim detected.")
        revision_brief.append("Replace the superlative with a specific, verifiable claim.")
    else:
        score = 0
        issues.append(f"{superlative_hits} superlative or exaggerated claims detected.")
        revision_brief.append(
            "Audit every claim. Replace superlatives with specific outcomes "
            "grounded in the retrieved brand context."
        )

    # Check 2: Claims grounded in retrieved context (0–7)
    if research.citations and len(research.citations) > 0:
        # At least some retrieval happened — brand facts are in play
        priority_in_copy = any(
            p.lower() in combined
            for p in research.brand_facts.customer_priorities
        )
        score += 7 if priority_in_copy else 3
        if not priority_in_copy:
            issues.append("Copy claims are not visibly grounded in the retrieved brand context.")
            revision_brief.append(
                "Tie at least one key claim to a retrieved customer priority or brand fact."
            )
    else:
        # No retrieval — can only verify against the request
        score += 4  # Neutral: no KB context to validate against

    return min(score, 15), issues, revision_brief


# ---------------------------------------------------------------------------
# Category 6 — Channel Native-ness  (0–5 pts)
# ---------------------------------------------------------------------------

def _score_channel_nativeness(
    content: ContentPackage,
) -> tuple[int, list[str], list[str]]:
    """Each asset speaks the native grammar of its channel."""
    issues: list[str] = []
    revision_brief: list[str] = []
    score = 0

    if len(content.social_posts) < 2:
        return 2, issues, revision_brief  # Neutral — not enough posts to compare

    # Check 1: Social post copy uniqueness across channels (0–3)
    post_copies = [flatten_text(post).lower() for post in content.social_posts]
    unique_copies = len(set(post_copies))
    if unique_copies == len(post_copies):
        score += 3
    elif unique_copies >= len(post_copies) // 2:
        score += 1
        issues.append("Some social posts share identical copy across different channels.")
        revision_brief.append(
            "Adapt each social post's tone and format to its channel — "
            "Instagram is visual/short, LinkedIn is credibility/long-form, "
            "Discord is conversational/community."
        )
    else:
        issues.append("Social posts appear copy-pasted across channels with different labels.")
        revision_brief.append("Rewrite each social post natively for its platform.")

    # Check 2: Email copy has a different register from ad copy (0–2)
    ad_words = set(flatten_ad_variants(content.ad_variants).lower().split())
    email_words = set(flatten_text(content.email_drafts).lower().split())
    overlap_ratio = len(ad_words & email_words) / max(len(ad_words | email_words), 1)

    if overlap_ratio < 0.5:
        score += 2  # Email reads differently from ad copy — good
    else:
        score += 0
        issues.append("Email body copy reads too similarly to the ad variants.")
        revision_brief.append(
            "Emails should feel personal and conversational, not like ads. "
            "Use 'I/we' language and address the reader directly."
        )

    return min(score, 5), issues, revision_brief


# ---------------------------------------------------------------------------
# Main reviewer
# ---------------------------------------------------------------------------

def review_creative(
    research: ResearchBrief,
    strategy: StrategyBrief,
    content: ContentPackage,
    iteration: int = 1,
    threshold: int = 75,
    original_goal: str = "",
) -> CreativeReview:
    """CMO-driven creative review across 6 quality dimensions (max 100 pts).

    Pass thresholds:
      < 60  → Rejected — discard and regenerate
      60-74 → Major revision required
      75-84 → Minor revision (passes pipeline with notes)
      85-94 → Approved — strong work
      95+   → Exceptional — rare, requires all categories near-maximum
    """
    import logging
    
    # Check for shape drift
    drift = False
    if content.ad_variants and any(not isinstance(ad, (ABTestCell, str, dict)) for ad in content.ad_variants):
        drift = True
    elif content.social_posts and any(not isinstance(p, dict) for p in content.social_posts):
        drift = True
    elif content.email_drafts and any(not isinstance(e, dict) for e in content.email_drafts):
        drift = True
        
    if drift:
        logging.getLogger(__name__).info("[CreativeReview] normalized LLM content structure")

    s1, i1, r1 = _score_single_minded_message(content, strategy)
    s2, i2, r2 = _score_audience_truth(research, content, original_goal)
    s3, i3, r3 = _score_brand_integrity(research, content)
    s4, i4, r4 = _score_conversion_logic(strategy, content)
    s5, i5, r5 = _score_claim_honesty(research, content)
    s6, i6, r6 = _score_channel_nativeness(content)

    category_scores = CategoryScores(
        single_minded_message=s1,
        audience_truth=s2,
        brand_integrity=s3,
        conversion_logic=s4,
        claim_honesty=s5,
        channel_nativeness=s6,
    )
    total = s1 + s2 + s3 + s4 + s5 + s6
    issues = i1 + i2 + i3 + i4 + i5 + i6
    revision_brief = r1 + r2 + r3 + r4 + r5 + r6

    return CreativeReview(
        passed=total >= threshold,
        score=total,
        category_scores=category_scores,
        issues=issues,
        revision_brief=revision_brief,
        iteration=iteration,
    )


# ---------------------------------------------------------------------------
# Campaign-level evaluation (structural checks)
# ---------------------------------------------------------------------------

def evaluate_campaign(
    strategy: StrategyBrief,
    content: ContentPackage,
    review: CreativeReview,
) -> EvaluationReport:
    category_scores = {
        "structure": round(
            sum([
                len(content.ad_variants) >= 5,
                len(content.email_drafts) >= 3,
                bool(content.landing_page_copy.get("primary_cta")),
            ])
            / 3 * 100
        ),
        "strategy": round(
            sum([bool(strategy.channel_plan), bool(strategy.success_metrics), bool(strategy.hypothesis)])
            / 3 * 100
        ),
        "creative": review.score,
    }
    checks = {
        "has_five_ads": len(content.ad_variants) >= 5,
        "has_three_emails": len(content.email_drafts) >= 3,
        "has_landing_cta": bool(content.landing_page_copy.get("primary_cta")),
        "has_channel_plan": bool(strategy.channel_plan),
        "has_metrics": bool(strategy.success_metrics),
        "passed_creative_review": review.passed,
        "has_strategy_hypothesis": bool(strategy.hypothesis),
    }
    score = round(sum(checks.values()) / len(checks) * 100)
    recommendations: list[str] = []

    if not checks["has_five_ads"]:
        recommendations.append("Add at least five ad variants for testing.")
    if not checks["has_three_emails"]:
        recommendations.append("Add at least three email drafts for a basic sequence.")
    if not checks["passed_creative_review"]:
        recommendations.extend(review.revision_brief[:3])
    if score == 100:
        recommendations.append("Ready for human review before launch.")

    return EvaluationReport(
        score=score,
        checks=checks,
        recommendations=recommendations,
        category_scores=category_scores,
    )


def summarize_package(package: CampaignPackage) -> str:
    cats = package.creative_review.category_scores
    return (
        f"Campaign score: {package.evaluation.score}/100\n"
        f"Positioning: {package.strategy.positioning}\n"
        f"Ads generated: {len(package.content.ad_variants)}\n"
        f"Emails generated: {len(package.content.email_drafts)}\n"
        f"Creative review: {package.creative_review.score}/100\n"
        f"  ↳ Single-minded message : {cats.single_minded_message}/25\n"
        f"  ↳ Audience truth        : {cats.audience_truth}/20\n"
        f"  ↳ Brand integrity       : {cats.brand_integrity}/20\n"
        f"  ↳ Conversion logic      : {cats.conversion_logic}/15\n"
        f"  ↳ Claim honesty         : {cats.claim_honesty}/15\n"
        f"  ↳ Channel native-ness   : {cats.channel_nativeness}/5\n"
        f"Category scores: structure {package.evaluation.category_scores.get('structure', 0)}/100, "
        f"strategy {package.evaluation.category_scores.get('strategy', 0)}/100, "
        f"creative {package.evaluation.category_scores.get('creative', 0)}/100\n"
        f"Strategy candidates: {len(package.strategy_candidates)}\n"
        f"Retrieved context files: {len(package.retrieved_context)}\n"
        f"Run diagnostics: retrieval={package.diagnostics.retrieval_quality}, "
        f"diversity={package.diagnostics.strategy_diversity}, "
        f"originality={package.diagnostics.content_originality}, "
        f"review_confidence={package.diagnostics.review_confidence}"
    )
