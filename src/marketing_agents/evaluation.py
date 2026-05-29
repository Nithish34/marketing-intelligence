from __future__ import annotations

from marketing_agents.contracts import CampaignPackage, ContentPackage, CreativeReview, EvaluationReport, ResearchBrief, StrategyBrief


def review_creative(
    research: ResearchBrief,
    strategy: StrategyBrief,
    content: ContentPackage,
    iteration: int = 1,
    threshold: int = 90,
) -> CreativeReview:
    issues: list[str] = []
    revision_brief: list[str] = []
    combined_text = " ".join(
        content.ad_variants
        + [post["copy"] for post in content.social_posts]
        + [draft["subject"] + " " + draft["body"] for draft in content.email_drafts]
        + list(content.landing_page_copy.values())
    ).lower()

    for forbidden in research.brand_facts.avoid:
        if forbidden.lower() in combined_text:
            issues.append(f"Content may violate avoid rule: {forbidden}")
            revision_brief.append(f"Remove or soften language related to {forbidden}.")

    if research.brand_facts.customer_priorities:
        priority_hits = sum(1 for item in research.brand_facts.customer_priorities if item.lower() in combined_text)
        if priority_hits == 0:
            issues.append("Content does not reflect retrieved customer priorities.")
            revision_brief.append(f"Use customer priority: {research.brand_facts.customer_priorities[0]}.")

    if research.brand_facts.content_style:
        style_hits = sum(1 for item in research.brand_facts.content_style if item.lower() in combined_text)
        if style_hits == 0:
            issues.append("Content does not reflect retrieved content style.")
            revision_brief.append(f"Make the tone more {research.brand_facts.content_style[0]}.")

    if not any(pillar.lower() in combined_text for pillar in strategy.messaging_pillars):
        issues.append("Content is not visibly tied to the strategy pillars.")
        revision_brief.append("Tie at least one asset to the primary messaging pillar.")

    cited_sources = " ".join(research.citations).lower()
    if research.brand_facts.citations and not cited_sources:
        issues.append("Research citations are missing from the campaign handoff.")
        revision_brief.append("Preserve chunk-level citations from retrieved context.")

    score = max(0, 100 - (len(issues) * 20))
    return CreativeReview(
        passed=score >= threshold,
        score=score,
        issues=issues,
        revision_brief=revision_brief,
        iteration=iteration,
    )


def evaluate_campaign(strategy: StrategyBrief, content: ContentPackage, review: CreativeReview) -> EvaluationReport:
    category_scores = {
        "structure": round(
            sum(
                [
                    len(content.ad_variants) >= 5,
                    len(content.email_drafts) >= 3,
                    bool(content.landing_page_copy.get("primary_cta")),
                ]
            )
            / 3
            * 100
        ),
        "strategy": round(
            sum([bool(strategy.channel_plan), bool(strategy.success_metrics), bool(strategy.hypothesis)])
            / 3
            * 100
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
        recommendations.extend(review.revision_brief)
    if score == 100:
        recommendations.append("Ready for human review before launch.")

    return EvaluationReport(
        score=score,
        checks=checks,
        recommendations=recommendations,
        category_scores=category_scores,
    )


def summarize_package(package: CampaignPackage) -> str:
    return (
        f"Campaign score: {package.evaluation.score}/100\n"
        f"Positioning: {package.strategy.positioning}\n"
        f"Ads generated: {len(package.content.ad_variants)}\n"
        f"Emails generated: {len(package.content.email_drafts)}\n"
        f"Creative review: {package.creative_review.score}/100\n"
        f"Category scores: structure {package.evaluation.category_scores.get('structure', 0)}/100, "
        f"strategy {package.evaluation.category_scores.get('strategy', 0)}/100, "
        f"creative {package.evaluation.category_scores.get('creative', 0)}/100\n"
        f"Strategy candidates: {len(package.strategy_candidates)}\n"
        f"Retrieved context files: {len(package.retrieved_context)}"
    )
