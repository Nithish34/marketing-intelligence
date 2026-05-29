# Multi-Agent Marketing System

V5 is a local, testable three-agent marketing campaign generator:

1. `ResearchAgent` turns product inputs plus retrieved knowledge into structured brand facts, audience insights, pain points, opportunities, assumptions, and citations.
2. `StrategyAgent` creates multiple candidate strategies, scores them, and selects the strongest positioning, messaging pillars, channel plan, funnel steps, success metrics, rejected angles, risk flags, and hypothesis.
3. `ContentAgent` turns the selected strategy into channel-aware campaign assets, then revises against a creative review threshold when grounding or brand-fit issues appear.

The system also includes the seven engineering areas you researched:

- system design: sequential three-agent pipeline
- tools + contract design: typed dataclass inputs and outputs
- RAG system design: chunk-level local retrieval with line citations, document-level filtering, retrieval reasons, and structured brand-fact extraction from `knowledge_base/`
- reliability engineering: validation, deterministic fallback model, strategy candidate scoring, creative review, and threshold-based revision loop
- security + safety: prompt-injection scanning for untrusted knowledge
- evaluation and observability: JSONL run logs, retrieved chunk traces, creative review scoring, strategy candidate scores, and campaign scoring
- product thinking: CLI subcommands for generation, RAG inspection, evaluation, config setup, and campaign export
- benchmarking: reusable scenario tests across industries with expected RAG source matching
- prompt readiness: editable prompt files for future LLM-backed agents

## Quick Start

```powershell
$env:PYTHONPATH='src'
py -m marketing_agents.cli generate --product "Acme CRM" --audience "small B2B sales teams" --goal "book demos" --tone "clear and confident"
```

Useful v5 commands:

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
  agents.py          Three agent implementations
  cli.py             Command-line interface
  benchmark.py       Scenario benchmark runner
  config.py          App configuration loading and default config writer
  contracts.py       Input/output data contracts
  exporters.py       Campaign JSON and Markdown export
  json_contracts.py  JSON extraction and contract helpers for LLM output
  model_factory.py   Model selection from config
  prompts.py         Prompt file loading
  brand_facts.py     Structured fact extraction from retrieved context
  evaluation.py      Creative review and campaign scoring
  llm.py             Model interface and deterministic local model
  observability.py   JSONL event logging
  pipeline.py        End-to-end orchestration
  rag.py             Chunk-level local retrieval and ranking
  safety.py          Prompt-injection and content guards
  validation.py      Contract validation
knowledge_base/
  sample_brand.md
prompts/
benchmark_scenarios.json
tests/
```

This v5 does not require an external LLM API. It keeps `RuleBasedMarketingModel` as the default, and includes an optional HTTP JSON model adapter for future LLM-backed runs.
