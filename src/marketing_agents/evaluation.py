from __future__ import annotations

from marketing_agents.contracts import CampaignPackage, ContentPackage, EvaluationReport, StrategyBrief


def evaluate_campaign(strategy: StrategyBrief, content: ContentPackage) -> EvaluationReport:
    checks = {
        "has_five_ads": len(content.ad_variants) >= 5,
        "has_three_emails": len(content.email_drafts) >= 3,
        "has_landing_cta": bool(content.landing_page_copy.get("primary_cta")),
        "has_channel_plan": bool(strategy.channel_plan),
        "has_metrics": bool(strategy.success_metrics),
    }
    score = round(sum(checks.values()) / len(checks) * 100)
    recommendations: list[str] = []

    if not checks["has_five_ads"]:
        recommendations.append("Add at least five ad variants for testing.")
    if not checks["has_three_emails"]:
        recommendations.append("Add at least three email drafts for a basic sequence.")
    if score == 100:
        recommendations.append("Ready for human review before launch.")

    return EvaluationReport(score=score, checks=checks, recommendations=recommendations)


def summarize_package(package: CampaignPackage) -> str:
    return (
        f"Campaign score: {package.evaluation.score}/100\n"
        f"Positioning: {package.strategy.positioning}\n"
        f"Ads generated: {len(package.content.ad_variants)}\n"
        f"Emails generated: {len(package.content.email_drafts)}\n"
        f"Retrieved context files: {len(package.retrieved_context)}"
    )

