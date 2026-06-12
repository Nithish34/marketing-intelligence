from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from marketing_agents.contracts import CampaignPackage


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "campaign"


def export_campaign(package: CampaignPackage, output_dir: Path | str, formats: list[str] | None = None) -> list[Path]:
    requested = formats or ["json", "md"]
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    base = f"{slugify(package.request.product)}-{stamp}"
    written: list[Path] = []

    if "json" in requested:
        json_path = root / f"{base}.json"
        json_path.write_text(json.dumps(asdict(package), indent=2), encoding="utf-8")
        written.append(json_path)

    if "md" in requested:
        md_path = root / f"{base}.md"
        md_path.write_text(render_markdown(package), encoding="utf-8")
        written.append(md_path)

    return written


def render_markdown(package: CampaignPackage) -> str:
    lines = [
        f"# {package.request.product} Campaign",
        "",
        f"**Audience:** {package.request.audience}",
        f"**Goal:** {package.request.goal}",
        f"**Campaign score:** {package.evaluation.score}/100",
        f"**Creative review:** {package.creative_review.score}/100",
        "",
        "## Positioning",
        package.strategy.positioning,
        "",
        "## Hypothesis",
        package.strategy.hypothesis,
        "",
        "## Messaging Pillars",
    ]
    lines.extend(f"- {pillar}" for pillar in package.strategy.messaging_pillars)
    lines.extend(["", "## Retrieved Chunks"])
    lines.extend(
        f"- {chunk.source}:{chunk.line_start}-{chunk.line_end} ({chunk.score}) {chunk.retrieval_reason}"
        for chunk in package.retrieved_context
    )
    lines.extend(["", "## Ad Variants"])
    for index, ad in enumerate(package.content.ad_variants, start=1):
        lines.extend(
            [
                f"### Test Cell {index}",
                f"- Control: {ad.control}",
                f"- Variant: {ad.variant}",
            ]
        )
    lines.extend(["", "## Social Posts"])
    lines.extend(f"- **{post['channel']}**: {post['copy']}" for post in package.content.social_posts)
    lines.extend(["", "## Emails"])
    for draft in package.content.email_drafts:
        lines.extend([f"### {draft['subject']}", draft["body"], ""])
    lines.extend(
        [
            "## Landing Page",
            f"**Headline:** {package.content.landing_page_copy.get('headline', '')}",
            f"**Subheadline:** {package.content.landing_page_copy.get('subheadline', '')}",
            f"**Primary CTA:** {package.content.landing_page_copy.get('primary_cta', '')}",
        ]
    )
    return "\n".join(lines).strip() + "\n"
