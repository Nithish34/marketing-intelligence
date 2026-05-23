from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from marketing_agents.contracts import CampaignRequest
from marketing_agents.evaluation import summarize_package
from marketing_agents.pipeline import MarketingPipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a v1 marketing campaign with three agents.")
    parser.add_argument("--product", required=True, help="Product or company name")
    parser.add_argument("--audience", required=True, help="Target audience")
    parser.add_argument("--goal", required=True, help="Campaign goal")
    parser.add_argument("--tone", default="clear, useful, and credible", help="Brand voice or tone")
    parser.add_argument(
        "--channels",
        default="paid social,email,landing page",
        help="Comma-separated channel list",
    )
    parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="Optional campaign constraint. Can be passed multiple times.",
    )
    parser.add_argument("--knowledge-base", default="knowledge_base", help="Directory with local .txt/.md context files")
    parser.add_argument("--log-path", default="runs/marketing_runs.jsonl", help="JSONL observability log path")
    parser.add_argument("--json", action="store_true", help="Print full JSON output")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    request = CampaignRequest(
        product=args.product,
        audience=args.audience,
        goal=args.goal,
        tone=args.tone,
        channels=[channel.strip() for channel in args.channels.split(",") if channel.strip()],
        constraints=args.constraint,
    )
    pipeline = MarketingPipeline.from_paths(
        knowledge_base_dir=Path(args.knowledge_base),
        log_path=Path(args.log_path),
    )
    package = pipeline.run(request)

    if args.json:
        print(json.dumps(asdict(package), indent=2))
        return

    print(summarize_package(package))
    print("\nMessaging pillars:")
    for pillar in package.strategy.messaging_pillars:
        print(f"- {pillar}")
    print("\nAd variants:")
    for ad in package.content.ad_variants:
        print(f"- {ad}")
    print("\nLanding page:")
    print(package.content.landing_page_copy["headline"])
    print(package.content.landing_page_copy["subheadline"])


if __name__ == "__main__":
    main()

