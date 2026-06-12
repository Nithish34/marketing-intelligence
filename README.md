# Multi-Agent Marketing System

V7 is a smart and reliable three-agent marketing campaign generator. It focuses on high-quality outputs, strict creative review, and hybrid lexical plus semantic knowledge retrieval, all while keeping a solid 3-agent pipeline:

1. `ResearchAgent` turns product inputs plus retrieved knowledge into structured brand facts, audience insights, pain points, opportunities, assumptions, and citations. It also translates raw business goals into customer-centric language.
2. `StrategyAgent` creates 4 genuine candidate strategy archetypes (stress-reduction, productivity-gain, habit-building, social-proof), penalizes them for lack of diversity, and selects the strongest positioning, messaging pillars, channel plan, funnel steps, success metrics, rejected angles, risk flags, and hypothesis.
3. `ContentAgent` turns the selected strategy into channel-aware campaign assets, then revises against a strict CMO-driven creative review threshold when grounding, honesty, or brand-fit issues appear.

## V7 Key Features

- **Strict CMO-Driven Creative Review**: Replaces generic scoring with a 6-category system (Single-Minded Message, Audience Truth, Brand Integrity, Conversion Logic, Claim Honesty, Channel Native-ness).
- **Strategy Diversity**: Generates distinct strategy archetypes rather than surface-level variants, with a built-in penalty for lexical convergence.
- **Hybrid RAG Ranking**: Field-level lexical retrieval where audience mismatch is heavily penalized (audience=4, product=3, goal=3, tone=2), plus optional Chroma semantic boosts and a hard absolute score floor to prevent irrelevant brand documents from contaminating results.
- **Goal Translation**: A layer that automatically maps business-centric goals (e.g., "increase signups") to customer-centric language (e.g., "take the first step") for all public-facing copy.
- **Adversarial Benchmarks**: Tests that ensure the system gracefully handles conflicting tone requests, mismatched audience knowledge bases, and sophisticated prompt injection attempts (roleplay jailbreaks, developer overrides).
- **Richer Observability**: Computes `RunDiagnostics` per-run to measure retrieval quality, strategy diversity, content originality, review confidence, and goal translation usage.
- **Optional LLM Modes**: Supports routing to a local Ollama instance (`OllamaMarketingModel`), or online models like OpenAI and Gemini (`OpenAIMarketingModel`, `GeminiMarketingModel`) for A/B testing against the deterministic fallback model.

## Quick Start

```powershell
$env:PYTHONPATH='src'
py -m marketing_agents.cli generate --product "Acme CRM" --audience "small B2B sales teams" --goal "book demos" --tone "clear and confident"
```

Useful commands:

```powershell
py -m marketing_agents.cli init-config
py -m marketing_agents.cli inspect-rag --product "StudyFlow AI" --audience "college students" --goal "increase app signups"
py -m marketing_agents.cli generate --product "StudyFlow AI" --audience "college students" --goal "increase app signups" --export json,md
py -m marketing_agents.cli evaluate outputs\your-campaign.json
py -m marketing_agents.cli benchmark
```

Add brand, product, and customer context as `.txt` or `.md` files in `knowledge_base/`. The retriever will select relevant chunks, keep line-level citations, explain why chunks matched, then extract facts such as value proposition, brand voice, avoid rules, customer priorities, preferred channels, and content style.

## Run Tests

```powershell
$env:PYTHONPATH='src'
py -m unittest discover -s tests
```

## Project Layout

```text
src/marketing_agents/
  agents.py          Three agent implementations (Research, Strategy, Content)
  cli.py             Command-line interface
  benchmark.py       Scenario benchmark runner
  config.py          App configuration loading and default config writer
  contracts.py       Input/output data contracts
  exporters.py       Campaign JSON and Markdown export
  goal_translator.py Goal translation module
  json_contracts.py  JSON extraction and contract helpers for LLM output
  model_factory.py   Model selection from config
  prompts.py         Prompt file loading
  brand_facts.py     Structured fact extraction from retrieved context
  evaluation.py      Creative review and campaign scoring
  llm.py             Model interface and deterministic local model
  observability.py   JSONL event logging and run diagnostics
  pipeline.py        End-to-end orchestration
  rag.py             Weighted chunk-level local retrieval and ranking
  safety.py          Prompt-injection and content guards
  validation.py      Contract validation
knowledge_base/
  sample_brand.md
prompts/
benchmark_scenarios.json
tests/
```

V7 keeps `RuleBasedMarketingModel` as the default for deterministic testing. It also includes an `HttpJsonMarketingModel` for future LLM-backed runs, and an `OllamaMarketingModel` for local testing.
