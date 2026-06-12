# Multi-Agent Marketing System - Complete Project Report (V7)

**Generated:** May 30, 2026  
**Project Version:** 0.1.0 (V7 Architecture)  

---

## 1. PROJECT OVERVIEW

### 1.1 Project Name
**Multi-Agent Marketing System (V7)**

### 1.2 Project Description
A local, testable three-agent marketing campaign generator that transforms product inputs and retrieved knowledge into comprehensive campaign packages. The V7 architecture focuses on high-quality outputs, strict creative review, hybrid lexical plus semantic knowledge retrieval, and observability, all while keeping a solid 3-agent pipeline. It supports deterministic rule-based models for development, as well as optional integration with Ollama, OpenAI, and Gemini LLMs.

### 1.3 Purpose
To automate the generation of marketing campaign assets through a sequential three-agent pipeline:
1. **ResearchAgent** - Turns product inputs and retrieved knowledge into structured brand facts, audience insights, and translates raw business goals into customer-centric language.
2. **StrategyAgent** - Creates 4 genuine candidate strategy archetypes, penalises them for lack of diversity, and selects the strongest positioning and messaging pillars.
3. **ContentAgent** - Generates channel-aware campaign assets and revises them against a strict CMO-driven creative review threshold.

### 1.4 Python Requirements
- **Minimum Python Version:** 3.10
- **Virtual Environment:** Not auto-configured; user must set `PYTHONPATH='src'` manually

---

## 2. V7 KEY FEATURES

- **Strict CMO-Driven Creative Review**: A 6-category evaluation system (Single-Minded Message, Audience Truth, Brand Integrity, Conversion Logic, Claim Honesty, Channel Native-ness) replacing generic scoring.
- **Strategy Diversity**: Generates distinct strategy archetypes (stress-reduction, productivity-gain, habit-building, social-proof) with a built-in penalty for lexical convergence.
- **Weighted RAG Ranking**: Field-level retrieval scoring where audience mismatch is heavily penalized (audience=4, product=3, goal=3, tone=2, channels=1), plus a hard absolute score floor to prevent irrelevant brand documents from contaminating results.
- **Goal Translation**: Automatically maps business-centric goals (e.g., "increase signups") to customer-centric language (e.g., "take the first step") for all public-facing copy.
- **Run Diagnostics (Observability)**: Computes quality signals per-run (retrieval quality, strategy diversity, content originality, review confidence, goal translation usage).
- **Optional LLM Modes**: Support for local `OllamaMarketingModel` and cloud-based `OpenAIMarketingModel` and `GeminiMarketingModel`, using an `HttpJsonMarketingModel` adapter.

---

## 3. PROJECT STRUCTURE & FILE ORGANIZATION

```text
multi-agent marketing system/
├── pyproject.toml                         # Project metadata and dependencies
├── README.md                              # Quick start guide
├── PROJECT_REPORT.md                      # Current comprehensive project report
├── marketing_agents.config.json           # Application configuration
├── benchmark_scenarios.json               # Input scenarios for benchmarking
├── knowledge_base/                        # Knowledge storage for RAG system
├── outputs/                               # Exported JSON and Markdown outputs
├── prompts/                               # Markdown prompt templates for LLMs
├── runs/                                  # Generated campaign logs (JSONL)
├── src/                                   # Source code
│   └── marketing_agents/
│       ├── __init__.py                    
│       ├── agents.py                      # Implementation of Research, Strategy, Content Agents
│       ├── cli.py                         # Command-line interface
│       ├── benchmark.py                   # Scenario benchmark runner
│       ├── config.py                      # Configuration loading
│       ├── exporters.py                   # Campaign JSON and Markdown export
│       ├── goal_translator.py             # Business to customer-centric goal translation mapping
│       ├── json_contracts.py              # JSON extraction and validation helpers
│       ├── model_factory.py               # Model instantiation based on config
│       ├── prompts.py                     # Prompt template loading
│       ├── contracts.py                   # Dataclass contracts for I/O
│       ├── brand_facts.py                 # Structured fact extraction
│       ├── evaluation.py                  # CMO-driven creative review and campaign scoring
│       ├── llm.py                         # RuleBased, Ollama, OpenAI, Gemini model integrations
│       ├── observability.py               # JSONL event logging
│       ├── pipeline.py                    # End-to-end orchestration
│       ├── rag.py                         # Weighted chunk-level local retrieval and ranking
│       ├── safety.py                      # Prompt injection and content guards
│       └── validation.py                  # Contract validation
└── tests/
    └── test_pipeline.py                   # Integration tests
```

---

## 4. CORE COMPONENTS & ARCHITECTURE

### 4.1 Agents (`src/marketing_agents/agents.py`)

#### ResearchAgent
- **Process**: Extracts brand facts from `RetrievedContext`, invokes the LLM/Model for research insights, and translates the business goal into customer-centric language using `goal_translator.py`. Implements a JSON repair retry loop for structural enforcement.
- **Output**: `ResearchBrief` (Brand facts, insights, competitors, translated_goal, etc.)

#### StrategyAgent
- **Process**: Generates 4 strategy archetypes:
  1. *Stress Reduction*: Emotional pain/anxiety relief.
  2. *Productivity Gain*: Measurable, rational efficiency gains.
  3. *Habit Building*: Identity change and long-term consistency.
  4. *Social Proof*: Peer validation and community.
- **Diversity Penalty**: Applies a lexical overlap penalty if candidate messaging pillars share > 60% of words, enforcing genuine strategic differentiation.
- **Output**: `StrategyBrief` (Selected strategy, channel plan, funnel steps, metrics).

#### ContentAgent
- **Process**: Generates channel-aware copy (ads, social, emails, landing pages) based on research and strategy.
- **Revision Loop**: Runs content through `review_creative()`. If it fails the threshold, appends the most critical revision note to the first ad variant and triggers a regeneration round (up to 3 times).
- **Output**: `ContentPackage`

### 4.2 RAG System (`src/marketing_agents/rag.py`)
- **Chunking**: Max 8 lines, 1200 chars, chunked by headers or short text lines.
- **Weighted Scoring**: Evaluates overlaps with query tokens. Heavily penalizes mismatch on critical fields: `audience (4)`, `product (3)`, `goal (3)`, `tone (2)`.
- **Absolute Floor**: Chunks scoring below a hard threshold (`MIN_ABSOLUTE_SCORE = 4`) are silently dropped, preventing unrelated documents from contaminating context.
- **Anti-gaming**: Prevents chunks that only match on channel names from dominating if no core concepts match.

### 4.3 Goal Translation (`src/marketing_agents/goal_translator.py`)
Provides static mapping from business-internal goals to customer-centric phrasing.
- e.g., "increase signups" -> "take the first step"
- e.g., "book demos" -> "see it in action"

### 4.4 LLM Interfaces (`src/marketing_agents/llm.py`)
- `RuleBasedMarketingModel`: Deterministic logic generating hardcoded copy based on inputs and brand facts. Crucial for stable integration tests.
- `HttpJsonMarketingModel`: Base class for HTTP API interactions using `response_format={"type": "json_object"}`.
- `OllamaMarketingModel`: Hits local Ollama via OpenAI-compatible endpoints (`/v1/chat/completions`). Supports longer timeouts for local inference.
- `OpenAIMarketingModel` & `GeminiMarketingModel`: Cloud adapters for GPT and Gemini with rate-limit retry logic built-in.

### 4.5 CMO-Driven Evaluation (`src/marketing_agents/evaluation.py`)
Instead of an arbitrary generic score, reviews are scored out of 100 based on 6 rigorous dimensions:
1. **Single-Minded Message (0-25)**: Checks if messaging pillars reflect clearly across variants, penalizing identical repetitive hooks.
2. **Audience Truth (0-20)**: Checks if customer priorities are present and ensures raw business goals haven't leaked verbatim into copy.
3. **Brand Integrity (0-20)**: Hard deductions for violating 'avoid' rules, plus penalties for generic buzzwords.
4. **Conversion Logic (0-15)**: Checks landing page CTA specificity and email clear actions.
5. **Claim Honesty (0-15)**: Hard floor (0 points) for unsupported guarantees; penalties for superlative/exaggerated words.
6. **Channel Native-ness (0-5)**: Checks if social post copy diverges appropriately across channels and differs from email/ad copy register.

### 4.6 Pipeline & Observability (`src/marketing_agents/pipeline.py` & `observability.py`)
- **MarketingPipeline**: Orchestrates safety checks, retrieval, all agents, evaluation loops, and finally calculates `RunDiagnostics`.
- **JsonlRunLogger**: Writes timestamped structural events (e.g., `request_received`, `content_revised`, `run_diagnostics_completed`) into `runs/marketing_runs.jsonl`.
- **Run Diagnostics**: Computes quality scalars per execution: `retrieval_quality`, `strategy_diversity`, `content_originality`, `review_confidence`, and `goal_translation_used`.

---

## 5. CLI USAGE & TESTING

### 5.1 CLI (`src/marketing_agents/cli.py`)
Run via `$env:PYTHONPATH='src'; py -m marketing_agents.cli <subcommand>`
- `generate`: Orchestrates the pipeline to generate assets. Options include `--export json,md`, `--json`.
- `inspect-rag`: Allows developers to see exact chunks, scores, and reasons retrieved for a given query.
- `benchmark`: Executes scenarios in `benchmark_scenarios.json` and tallies accuracy.
- `evaluate`: Re-evaluates an exported JSON campaign.
- `init-config`: Bootstraps `marketing_agents.config.json`.

### 5.2 Test Suite
Powered by `unittest` in the `tests/` directory. Ensures the pipeline works natively with `RuleBasedMarketingModel`, validating prompt injection safeguards, expected evaluation scores, and data contracts.

## 6. CONCLUSION
The Multi-Agent Marketing System V7 provides a robust platform for algorithmic marketing generation. Its major innovations (strict CMO evaluation, diversity penalization, hybrid RAG, semantic diagnostics, and goal translation) make its generative output less prone to "LLM sameness" and much closer to professional marketing standards. It offers complete transparency into its decisions via JSONL logs and structured data contracts.
