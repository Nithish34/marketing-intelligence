"""
V6 vs V7 A/B Benchmark Harness
===============================
Runs the same campaign prompts through:
  - V6 mode: lexical-only RAG (collection disabled)
  - V7 mode: hybrid semantic+lexical RAG

Measures per-run:
  - Creative review score
  - Strategy diversity
  - Content originality
  - Retrieval quality
  - Generic buzzword count
  - Semantic boost count
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path("src")))

from marketing_agents.config import AppConfig
from marketing_agents.contracts import CampaignRequest
from marketing_agents.evaluation import GENERIC_BUZZWORDS
from marketing_agents.agents import flatten_text
from marketing_agents.pipeline import MarketingPipeline


@dataclass
class ABResult:
    name: str
    mode: str  # "v6_lexical" or "v7_hybrid"
    creative_score: int
    strategy_diversity: int
    content_originality: int
    retrieval_quality: int
    generic_buzzword_count: int
    semantic_boost_count: int
    elapsed_seconds: float


SCENARIOS = [
    CampaignRequest(product="SmartCRM", audience="small B2B sales teams",
                    goal="increase pipeline visibility", tone="clear, practical",
                    channels=["LinkedIn", "email"]),
    CampaignRequest(product="StudyFlow", audience="college students",
                    goal="improve study habits", tone="motivating, clear",
                    channels=["Instagram", "YouTube", "email"]),
    CampaignRequest(product="ShieldOps", audience="enterprise security teams",
                    goal="reduce breach response time", tone="precise, credible",
                    channels=["LinkedIn", "email", "webinars"]),
    CampaignRequest(product="FreshBrew", audience="coffee enthusiasts",
                    goal="grow subscription base", tone="friendly, authentic",
                    channels=["Instagram", "email", "landing page"]),
]


def count_generic(package) -> int:
    combined = (
        flatten_text(package.content.ad_variants)
        + " " + flatten_text(package.content.social_posts)
        + " " + flatten_text(package.content.email_drafts)
        + " " + flatten_text(package.content.landing_page_copy)
    ).lower()
    return sum(1 for b in GENERIC_BUZZWORDS if b in combined)


def count_semantic_boosts(package) -> int:
    return sum(1 for c in package.retrieved_context if "semantic boost" in c.retrieval_reason)


def run_scenario(request: CampaignRequest, mode: str, config: AppConfig) -> ABResult:
    pipeline = MarketingPipeline.from_config(config)

    if mode == "v6_lexical":
        # Disable semantic search by nulling the collection
        pipeline.knowledge_base.collection = None

    t0 = time.perf_counter()
    package = pipeline.run(request)
    elapsed = time.perf_counter() - t0

    return ABResult(
        name=request.product,
        mode=mode,
        creative_score=package.creative_review.score,
        strategy_diversity=package.diagnostics.strategy_diversity,
        content_originality=package.diagnostics.content_originality,
        retrieval_quality=package.diagnostics.retrieval_quality,
        generic_buzzword_count=count_generic(package),
        semantic_boost_count=count_semantic_boosts(package),
        elapsed_seconds=round(elapsed, 2),
    )


def main():
    loaded = AppConfig.load()
    # Force rule-based mode so benchmark runs without external LLM
    config = AppConfig(
        knowledge_base_dir=loaded.knowledge_base_dir,
        log_path=loaded.log_path,
        output_dir=loaded.output_dir,
        default_channels=loaded.default_channels,
        review_threshold=loaded.review_threshold,
        max_revision_rounds=loaded.max_revision_rounds,
        max_rag_chunks=loaded.max_rag_chunks,
        model_mode="rule-based",
        prompt_dir=loaded.prompt_dir,
        benchmark_path=loaded.benchmark_path,
        research_mode=None,
        strategy_mode=None,
        content_mode=None,
        review_mode=None,
    )
    results: list[ABResult] = []

    for request in SCENARIOS:
        print(f"\n--- {request.product} ---")
        for mode in ("v6_lexical", "v7_hybrid"):
            print(f"  Running {mode}...", end=" ", flush=True)
            result = run_scenario(request, mode, config)
            results.append(result)
            print(f"creative={result.creative_score}, "
                  f"diversity={result.strategy_diversity}, "
                  f"retrieval={result.retrieval_quality}, "
                  f"generic={result.generic_buzzword_count}, "
                  f"boosts={result.semantic_boost_count}, "
                  f"time={result.elapsed_seconds}s")

    # Summary table
    print("\n" + "=" * 100)
    print(f"{'Scenario':<14} {'Mode':<14} {'Creative':>8} {'Diversity':>10} {'Retrieval':>10} "
          f"{'Generic':>8} {'Boosts':>7} {'Time':>7}")
    print("-" * 100)

    v6_scores = []
    v7_scores = []
    for r in results:
        print(f"{r.name:<14} {r.mode:<14} {r.creative_score:>8} {r.strategy_diversity:>10} "
              f"{r.retrieval_quality:>10} {r.generic_buzzword_count:>8} "
              f"{r.semantic_boost_count:>7} {r.elapsed_seconds:>6.1f}s")
        if r.mode == "v6_lexical":
            v6_scores.append(r.creative_score)
        else:
            v7_scores.append(r.creative_score)

    print("-" * 100)
    v6_avg = sum(v6_scores) / len(v6_scores) if v6_scores else 0
    v7_avg = sum(v7_scores) / len(v7_scores) if v7_scores else 0
    delta = v7_avg - v6_avg
    print(f"{'AVERAGE':<14} {'v6_lexical':<14} {v6_avg:>8.1f}")
    print(f"{'AVERAGE':<14} {'v7_hybrid':<14} {v7_avg:>8.1f}")
    print(f"{'DELTA':<14} {'v7 - v6':<14} {delta:>+8.1f}")

    if delta > 0:
        print(f"\n[PASS] V7 hybrid RAG improves average creative score by +{delta:.1f}")
    elif delta == 0:
        print(f"\n[INFO] V7 hybrid RAG scores equal to V6 (gains may show with LLM models)")
    else:
        print(f"\n[WARN] V7 hybrid RAG scored lower by {delta:.1f} -- investigate")

    # Save results
    out = Path("runs/v6_vs_v7_benchmark.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")
    print(f"\nResults saved to {out}")


if __name__ == "__main__":
    main()
