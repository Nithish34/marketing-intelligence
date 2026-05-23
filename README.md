# Multi-Agent Marketing System

V1 is a local, testable three-agent marketing campaign generator:

1. `ResearchAgent` turns product inputs plus retrieved knowledge into audience, competitor, pain-point, and opportunity research.
2. `StrategyAgent` turns research into positioning, messaging pillars, channels, funnel steps, and success metrics.
3. `ContentAgent` turns strategy into campaign assets: ads, social posts, emails, and landing page copy.

The system also includes the seven engineering areas you researched:

- system design: sequential three-agent pipeline
- tools + contract design: typed dataclass inputs and outputs
- RAG system design: local document retrieval from `knowledge_base/`
- reliability engineering: validation, correction hooks, deterministic fallback model
- security + safety: prompt-injection scanning for untrusted knowledge
- evaluation and observability: JSONL run logs and campaign scoring
- product thinking: a simple CLI that asks for business inputs and returns a campaign package

## Quick Start

```powershell
$env:PYTHONPATH='src'
py -m marketing_agents.cli --product "Acme CRM" --audience "small B2B sales teams" --goal "book demos" --tone "clear and confident"
```

Add brand, product, and customer context as `.txt` or `.md` files in `knowledge_base/`. The retriever will use those files as local RAG context.

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
  contracts.py       Input/output data contracts
  evaluation.py      Campaign scoring
  llm.py             Model interface and deterministic local model
  observability.py   JSONL event logging
  pipeline.py        End-to-end orchestration
  rag.py             Local document retrieval
  safety.py          Prompt-injection and content guards
  validation.py      Contract validation
knowledge_base/
  sample_brand.md
tests/
```

This v1 does not require an external LLM API. Replace `RuleBasedMarketingModel` in `llm.py` with an API-backed implementation when you are ready.
