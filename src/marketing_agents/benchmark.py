from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from marketing_agents.config import AppConfig
from marketing_agents.contracts import CampaignRequest
from marketing_agents.pipeline import MarketingPipeline


@dataclass(frozen=True)
class BenchmarkResult:
    name: str
    score: int
    creative_score: int
    expected_source: str
    matched_expected_source: bool
    retrieved_sources: list[str]
    semantic_boost_applied: bool = False
    goal_translation_used: bool = False


def load_scenarios(path: Path | str = "benchmark_scenarios.json") -> list[dict[str, object]]:
    scenario_path = Path(path)
    if not scenario_path.exists():
        return []
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def run_benchmark(config: AppConfig, scenarios_path: Path | str = "benchmark_scenarios.json") -> list[BenchmarkResult]:
    scenarios = load_scenarios(scenarios_path)
    results: list[BenchmarkResult] = []

    for scenario in scenarios:
        request = CampaignRequest(
            product=str(scenario["product"]),
            audience=str(scenario["audience"]),
            goal=str(scenario["goal"]),
            tone=str(scenario.get("tone", "clear, useful, and credible")),
            channels=list(scenario.get("channels", config.default_channels or ["paid social", "email", "landing page"])),
        )
        package = MarketingPipeline.from_config(config).run(request)
        retrieved_sources = [Path(chunk.source).name for chunk in package.retrieved_context]
        expected_source_raw = scenario.get("expected_source")
        expected_source = str(expected_source_raw) if expected_source_raw else ""
        results.append(
            BenchmarkResult(
                name=str(scenario.get("name", request.product)),
                score=package.evaluation.score,
                creative_score=package.creative_review.score,
                expected_source=expected_source,
                matched_expected_source=expected_source in retrieved_sources if expected_source else True,
                retrieved_sources=sorted(set(retrieved_sources)),
                semantic_boost_applied=package.diagnostics.semantic_boost_applied,
                goal_translation_used=package.diagnostics.goal_translation_used,
            )
        )

    return results


def summarize_benchmark(results: list[BenchmarkResult]) -> str:
    if not results:
        return "No benchmark scenarios found."

    average = round(sum(result.score for result in results) / len(results))
    matched = sum(1 for result in results if result.matched_expected_source)
    boosts = sum(1 for result in results if result.semantic_boost_applied)
    lines = [
        f"Benchmark scenarios: {len(results)}",
        f"Average campaign score: {average}/100",
        f"Expected-source matches: {matched}/{len(results)}",
        f"Semantic search boosts: {boosts}/{len(results)}",
        "",
    ]
    for result in results:
        status = "match" if result.matched_expected_source else "miss"
        lines.append(
            f"- {result.name}: campaign {result.score}/100, creative {result.creative_score}/100, RAG {status}"
        )
    return "\n".join(lines)
