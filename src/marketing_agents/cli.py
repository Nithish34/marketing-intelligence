from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from marketing_agents.config import AppConfig, write_default_config
from marketing_agents.benchmark import run_benchmark, summarize_benchmark
from marketing_agents.contracts import CampaignRequest
from marketing_agents.evaluation import summarize_package
from marketing_agents.exporters import export_campaign
from marketing_agents.pipeline import MarketingPipeline
from marketing_agents.rag import LocalKnowledgeBase


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the v5 multi-agent marketing system.")
    parser.add_argument("--config", default=None, help="Optional config JSON path")

    subparsers = parser.add_subparsers(dest="command")

    generate = subparsers.add_parser("generate", help="Generate a complete campaign package")
    add_campaign_args(generate)
    generate.add_argument("--json", action="store_true", help="Print full JSON output")
    generate.add_argument(
        "--export",
        default="",
        help="Comma-separated export formats: json,md. Empty means no export.",
    )
    generate.add_argument("--output-dir", default=None, help="Override configured output directory")

    inspect = subparsers.add_parser("inspect-rag", help="Show retrieved RAG chunks for a campaign request")
    add_campaign_args(inspect)
    inspect.add_argument("--limit", type=int, default=None, help="Override max RAG chunks")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate an exported campaign JSON file")
    evaluate.add_argument("campaign_json", help="Path to an exported campaign .json file")

    init_config = subparsers.add_parser("init-config", help="Create a default config file")
    init_config.add_argument("--path", default="marketing_agents.config.json", help="Config path to create")

    benchmark = subparsers.add_parser("benchmark", help="Run benchmark campaign scenarios")
    benchmark.add_argument("--scenarios", default=None, help="Override benchmark scenarios JSON path")
    benchmark.add_argument("--json", action="store_true", help="Print benchmark results as JSON")

    return parser


def add_campaign_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--product", required=True, help="Product or company name")
    parser.add_argument("--audience", required=True, help="Target audience")
    parser.add_argument("--goal", required=True, help="Campaign goal")
    parser.add_argument("--tone", default="clear, useful, and credible", help="Brand voice or tone")
    parser.add_argument(
        "--channels",
        default=None,
        help="Comma-separated channel list. Defaults to config or built-in channels.",
    )
    parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="Optional campaign constraint. Can be passed multiple times.",
    )
    parser.add_argument("--knowledge-base", default=None, help="Override configured knowledge base directory")
    parser.add_argument("--log-path", default=None, help="Override configured JSONL log path")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "generate"

    if command == "init-config":
        path = write_default_config(args.path)
        print(f"Config ready: {path}")
        return

    config = AppConfig.load(args.config)

    if command == "evaluate":
        evaluate_export(Path(args.campaign_json))
        return

    if command == "benchmark":
        run_benchmark_command(args, config)
        return

    if command == "generate":
        run_generate(args, config)
        return

    if command == "inspect-rag":
        run_inspect_rag(args, config)
        return

    parser.print_help()


def request_from_args(args: argparse.Namespace, config: AppConfig) -> CampaignRequest:
    channels = parse_channels(args.channels)
    if not channels:
        channels = config.default_channels or ["paid social", "email", "landing page"]

    return CampaignRequest(
        product=args.product,
        audience=args.audience,
        goal=args.goal,
        tone=args.tone,
        channels=channels,
        constraints=args.constraint,
    )


def parse_channels(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [channel.strip() for channel in raw.split(",") if channel.strip()]


def pipeline_from_args(args: argparse.Namespace, config: AppConfig) -> MarketingPipeline:
    effective = AppConfig(
        knowledge_base_dir=args.knowledge_base or config.knowledge_base_dir,
        log_path=args.log_path or config.log_path,
        output_dir=config.output_dir,
        default_channels=config.default_channels,
        review_threshold=config.review_threshold,
        max_revision_rounds=config.max_revision_rounds,
        max_rag_chunks=config.max_rag_chunks,
        model_mode=config.model_mode,
    )
    return MarketingPipeline.from_config(effective)


def run_generate(args: argparse.Namespace, config: AppConfig) -> None:
    request = request_from_args(args, config)
    pipeline = pipeline_from_args(args, config)
    package = pipeline.run(request)

    if args.export:
        output_dir = Path(args.output_dir or config.output_dir)
        paths = export_campaign(package, output_dir, parse_channels(args.export))
        print("Exported:")
        for path in paths:
            print(f"- {path}")

    if args.json:
        print(json.dumps(asdict(package), indent=2))
        return

    print_package_summary(package)


def run_inspect_rag(args: argparse.Namespace, config: AppConfig) -> None:
    request = request_from_args(args, config)
    knowledge_base = LocalKnowledgeBase(args.knowledge_base or config.knowledge_base_dir)
    chunks = knowledge_base.retrieve(request, limit=args.limit or config.max_rag_chunks)

    print(f"Retrieved chunks: {len(chunks)}")
    for chunk in chunks:
        print(f"- {chunk.source}:{chunk.line_start}-{chunk.line_end} ({chunk.score})")
        print(f"  reason: {chunk.retrieval_reason}")
        print(f"  text: {chunk.text[:180].replace(chr(10), ' ')}")


def evaluate_export(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    evaluation = data.get("evaluation", {})
    creative = data.get("creative_review", {})
    print(f"Campaign score: {evaluation.get('score', 'unknown')}/100")
    print(f"Creative review: {creative.get('score', 'unknown')}/100")
    category_scores = evaluation.get("category_scores", {})
    if category_scores:
        print("Category scores:")
        for name, score in category_scores.items():
            print(f"- {name}: {score}/100")
    recommendations = evaluation.get("recommendations", [])
    if recommendations:
        print("Recommendations:")
        for item in recommendations:
            print(f"- {item}")


def run_benchmark_command(args: argparse.Namespace, config: AppConfig) -> None:
    results = run_benchmark(config, args.scenarios or config.benchmark_path)
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
        return
    print(summarize_benchmark(results))


def print_package_summary(package) -> None:
    print(summarize_package(package))
    print("\nMessaging pillars:")
    for pillar in package.strategy.messaging_pillars:
        print(f"- {pillar}")
    print(f"\nSelected strategy hypothesis: {package.strategy.hypothesis}")
    print("\nStrategy candidates:")
    for candidate in package.strategy_candidates:
        print(f"- {candidate.name}: {candidate.score}/100")
    print("\nBrand facts:")
    print(f"- Voice: {', '.join(package.research.brand_facts.voice) or 'not retrieved'}")
    print(f"- Customer priorities: {', '.join(package.research.brand_facts.customer_priorities) or 'not retrieved'}")
    print(f"- Preferred channels: {', '.join(package.research.brand_facts.preferred_channels) or 'not retrieved'}")
    print("\nRetrieved chunks:")
    for chunk in package.retrieved_context:
        print(f"- {chunk.source}:{chunk.line_start}-{chunk.line_end} ({chunk.score}) {chunk.retrieval_reason}")
    print("\nAd variants:")
    for ad in package.content.ad_variants:
        print(f"- {ad}")
    print("\nSocial posts:")
    for post in package.content.social_posts:
        print(f"- {post['channel']}: {post['copy']}")
    print("\nLanding page:")
    print(package.content.landing_page_copy["headline"])
    print(package.content.landing_page_copy["subheadline"])


if __name__ == "__main__":
    main()
