# Multi-Agent Marketing System Documentary

## Project Identity

The project is called **Multi-Agent Marketing System**.

It is a local Python-based marketing campaign generator. The system takes a product, audience, goal, tone, and channel list, then produces a complete marketing campaign package using a structured multi-agent workflow.

The current version is best described as:

**V7 Hybrid-RAG Multi-Agent Marketing Campaign Generator**

It combines:

- Multi-agent orchestration
- Local and optional LLM-based generation
- Brand knowledge retrieval
- Safety filtering
- Goal translation
- Strategy diversity
- Creative review
- Campaign scoring
- Exporting
- Benchmarking
- Observability logs

The main package lives in:

```text
src/marketing_agents
```

## The Big Idea

The project is built around a realistic marketing workflow.

Instead of asking one model to write a campaign in a single step, the system splits the work into specialist stages:

1. Research
2. Strategy
3. Content
4. Creative Review
5. Evaluation
6. Export and Logging

This makes the output easier to inspect, test, improve, and trust.

A user can give a request like:

```powershell
marketing-agents generate --product "StudyFlow AI" --audience "college students" --goal "increase app signups"
```

The system then retrieves brand context, creates a research brief, develops multiple strategies, chooses the best one, writes campaign content, reviews it, revises if needed, evaluates it, logs it, and optionally exports it.

## Core Architecture

The system is orchestrated by:

```text
src/marketing_agents/pipeline.py
```

The pipeline flow is:

```text
CampaignRequest
    ↓
Validation + Safety Check
    ↓
Knowledge Retrieval / RAG
    ↓
ResearchAgent
    ↓
StrategyAgent
    ↓
ContentAgent
    ↓
Creative Review
    ↓
Revision Loop
    ↓
Evaluation
    ↓
Diagnostics
    ↓
CampaignPackage
    ↓
Export / Logs / Memory
```

The project uses dataclass contracts so every stage passes structured objects instead of loose dictionaries.

Important contracts live in:

```text
src/marketing_agents/contracts.py
```

Key objects include:

- `CampaignRequest`
- `RetrievedContext`
- `BrandFacts`
- `ResearchBrief`
- `StrategyBrief`
- `StrategyCandidate`
- `ABTestCell`
- `ContentPackage`
- `CreativeReview`
- `EvaluationReport`
- `RunDiagnostics`
- `CampaignPackage`

## The Three Agents

### 1. ResearchAgent

The Research Agent is implemented in:

```text
src/marketing_agents/agents.py
```

The Research Agent takes the campaign request and retrieved knowledge-base chunks.

It extracts brand facts such as:

- Value proposition
- Brand voice
- Avoid rules
- Customer priorities
- Preferred channels
- Content style
- Citations

Then it creates a research brief with:

- Audience insights
- Competitors
- Pain points
- Opportunities
- Assumptions
- Citations

It also translates business goals into customer-friendly language.

Examples:

```text
"increase app signups" -> "take the first step"
"book more demos" -> "see it in action"
```

That translation logic lives in:

```text
src/marketing_agents/goal_translator.py
```

### 2. StrategyAgent

The Strategy Agent creates four strategy candidates instead of one.

The four archetypes are:

1. **Stress Reduction**
   Focuses on relief, pressure, anxiety, and overwhelm.

2. **Productivity Gain**
   Focuses on efficiency, time saved, output, and measurable improvement.

3. **Habit Building**
   Focuses on consistency, identity, and repeat behavior.

4. **Social Proof**
   Focuses on peers, community, belonging, and validation.

Each strategy gets scored. The system then applies a diversity penalty if the candidates are too similar.

This avoids the common problem where multiple generated strategies sound different on the surface but are actually saying the same thing.

### 3. ContentAgent

The Content Agent turns the selected strategy into usable campaign assets.

It generates:

- A/B ad test cells
- Social posts
- Email drafts
- Landing page copy
- Revision notes

The current contract uses:

```python
ABTestCell(control="...", variant="...")
```

That means ad variants are structured A/B test pairs, not plain strings.

This was one of the major fixes made in the latest implementation pass.

## Knowledge Base And RAG

The knowledge base lives in:

```text
knowledge_base
```

It contains brand context files for many industries, including:

- Edtech
- Skincare ecommerce
- Cybersecurity SaaS
- Fintech budgeting
- Healthcare clinic
- Restaurant cafe
- Nonprofit donation
- AI productivity
- B2B CRM
- Logistics
- Fitness
- Gaming
- Legal services
- Travel hotel

The retrieval system lives in:

```text
src/marketing_agents/rag.py
```

The current project uses **hybrid retrieval**:

1. Lexical retrieval
   - Token matching
   - Weighted field scoring
   - Product, audience, goal, tone, and channel awareness

2. Semantic retrieval
   - Optional ChromaDB-based semantic boost
   - Cached in `.chroma_cache`

Retrieval is intentionally strict. Audience mismatch is heavily penalized so the wrong brand file does not contaminate the campaign.

For example, a finance executive campaign should not accidentally retrieve a teen gaming brand just because both mention broad words like community or growth.

## Safety Layer

Safety is handled in:

```text
src/marketing_agents/safety.py
```

The system scans both user input and knowledge-base text for prompt injection patterns.

Examples it rejects:

- `ignore previous instructions`
- `reveal your prompt`
- `developer message`
- `system prompt`
- `api key`
- `jailbreak`
- `you are now DAN`
- `override your constraints`

This protects the pipeline from treating untrusted brand documents as instructions.

## Creative Review

The creative review system lives in:

```text
src/marketing_agents/evaluation.py
```

It uses a CMO-style scoring framework with six categories:

1. **Single-Minded Message**: 25 points
2. **Audience Truth**: 20 points
3. **Brand Integrity**: 20 points
4. **Conversion Logic**: 15 points
5. **Claim Honesty**: 15 points
6. **Channel Native-ness**: 5 points

Total: 100 points.

This is more realistic than a simple pass/fail check. It catches problems like:

- Generic marketing language
- Weak CTAs
- Unsupported claims
- Brand avoid-rule violations
- Copy that leaks business goals into customer-facing language
- Social posts that are copy-pasted across channels
- Ads that do not reflect strategy pillars

The review threshold is currently `75`.

If content fails, the pipeline revises it up to the configured maximum revision rounds.

## Model System

The model layer lives in:

```text
src/marketing_agents/llm.py
```

The system supports:

1. **RuleBasedMarketingModel**
   - Deterministic
   - Local
   - Used for tests
   - No external API needed

2. **HttpJsonMarketingModel**
   - Generic HTTP JSON model adapter

3. **OllamaMarketingModel**
   - Local Ollama models

4. **OpenAIMarketingModel**
   - OpenAI API-compatible path

5. **GeminiMarketingModel**
   - Gemini OpenAI-compatible endpoint

Model selection is handled by:

```text
src/marketing_agents/model_factory.py
```

Configuration is handled by:

```text
src/marketing_agents/config.py
```

The current default is deterministic `rule-based`, so the project works locally without requiring Ollama.

## CLI

The CLI lives in:

```text
src/marketing_agents/cli.py
```

Main commands:

```powershell
marketing-agents generate
marketing-agents inspect-rag
marketing-agents evaluate
marketing-agents benchmark
marketing-agents init-config
```

Examples:

```powershell
$env:PYTHONPATH='src'
py -m marketing_agents.cli generate --product "StudyFlow AI" --audience "college students" --goal "increase app signups"
```

```powershell
py -m marketing_agents.cli inspect-rag --product "StudyFlow AI" --audience "college students" --goal "increase app signups"
```

```powershell
py -m marketing_agents.cli benchmark
```

## Exports

Exports are handled in:

```text
src/marketing_agents/exporters.py
```

The system can export campaigns as:

- JSON
- Markdown

Markdown renders A/B ads clearly:

```markdown
### Test Cell 1
- Control: ...
- Variant: ...
```

This was fixed because earlier exports were showing dataclass representations instead of human-readable ad copy.

## Observability

The system logs events to JSONL through:

```text
src/marketing_agents/observability.py
```

Logged events include:

- Request received
- Context retrieved
- Research completed
- Strategy candidates completed
- Strategy selected
- Content completed
- Creative review completed
- Revision completed
- Evaluation completed
- Diagnostics completed
- Campaign completed

This makes each run inspectable after the fact.

## Diagnostics

Every campaign gets `RunDiagnostics`.

Diagnostics include:

- Retrieval quality
- Strategy diversity
- Content originality
- Review confidence
- Whether goal translation was used
- Whether semantic boost was applied

This helps explain why a campaign performed well or poorly.

## Benchmarking

Benchmarking lives in:

```text
src/marketing_agents/benchmark.py
```

The benchmark scenarios are defined in:

```text
benchmark_scenarios.json
```

There is also a special A/B benchmark harness:

```text
src/marketing_agents/benchmark_ab.py
```

That compares:

- V6 lexical-only retrieval
- V7 hybrid semantic plus lexical retrieval

This is why some intentional V6 references remain.

## How We Built The Current State

### Step 1: Started With A Three-Agent Marketing Pipeline

The first major design decision was to split generation into Research, Strategy, and Content rather than using a single prompt.

This gave the system structure and made it easier to test each stage.

### Step 2: Added Typed Contracts

Dataclasses were introduced so every stage had a clear input and output shape.

This reduced ambiguity between agents.

### Step 3: Built A Local Rule-Based Model

A deterministic model was added so the system could run without external APIs.

This made tests reliable.

### Step 4: Added Local Knowledge Retrieval

The `knowledge_base` folder became the project source of brand truth.

The RAG layer retrieved relevant chunks based on product, audience, goal, tone, and channels.

### Step 5: Added Brand Fact Extraction

The system learned to extract voice, avoid rules, customer priorities, preferred channels, and content style from retrieved documents.

### Step 6: Added Safety Filtering

Prompt injection checks were added for user input and retrieved knowledge files.

This made the system safer against malicious or instruction-like text.

### Step 7: Added Strategy Candidates

Instead of one strategy, the Strategy Agent began producing multiple candidates.

Later this became four distinct archetypes:

- Stress reduction
- Productivity gain
- Habit building
- Social proof

### Step 8: Added Creative Review

A stricter CMO-style review system replaced simple scoring.

The review now checks brand fit, audience fit, conversion logic, claim honesty, and channel nativeness.

### Step 9: Added Goal Translation

Business goals like `increase signups` were translated into customer-facing language like `take the first step`.

This prevented awkward internal business language from leaking into ads and emails.

### Step 10: Added Observability And Diagnostics

JSONL logging and run diagnostics were added so every campaign could be inspected after generation.

### Step 11: Added Optional LLM Modes

The project expanded beyond rule-based generation to support:

- Ollama
- OpenAI
- Gemini
- Generic HTTP JSON models

### Step 12: Added Hybrid Semantic Retrieval

ChromaDB support was added so lexical retrieval could be boosted with semantic similarity.

This became the key V7 capability.

### Step 13: Added Benchmarks And Adversarial Tests

Tests were added for:

- Prompt injection
- Wrong-audience retrieval
- Brand/tone contradiction
- Strategy shape drift
- Creative review robustness
- Benchmark source matching

### Step 14: Found Current Version Drift

During review, the project had mixed labels:

- Some docs said V6
- Some metadata said v5
- Some code had V7 behavior

The current identity was standardized as V7.

### Step 15: Fixed The Ad Variant Contract

This was the biggest recent fix.

Problem:

- Code used `ABTestCell`
- Prompts asked for plain strings
- Tests sometimes joined ads as strings
- Creative review treated structured ads as shape drift
- Rule-based model only generated 2 ads while tests expected 5

Fix:

- Standardized on `ABTestCell`
- Updated prompts to request `{ control, variant }`
- Updated deterministic model to produce 5 A/B cells
- Updated review to score both control and variant
- Updated exports and CLI output
- Updated tests

### Step 16: Made Defaults Deterministic

The default config was changed so normal local runs use `rule-based`.

Ollama is still supported, but no longer unexpectedly required.

### Step 17: Cleaned Generated Artifacts

`.gitignore` was expanded to ignore:

- `__pycache__`
- `*.pyc`
- `.pytest_cache`
- `.venv`
- `*.egg-info`
- `outputs`
- `runs`
- `memory/*.json`
- `.chroma_cache`

### Step 18: Verified With Tests

The local venv Python was blocked by Windows permissions, and bundled Python did not have `pytest`.

So the project was verified with:

```powershell
$env:PYTHONPATH='src'
C:\Users\nithi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
```

Result:

```text
Ran 15 tests
OK
```

## Current State Summary

The current project is a working V7 multi-agent marketing system with:

- Structured campaign request handling
- Hybrid RAG retrieval
- Brand fact extraction
- Goal translation
- Four strategy archetypes
- A/B ad test cells
- Channel-aware content generation
- Strict creative review
- Revision loop
- Evaluation scoring
- Run diagnostics
- JSONL observability
- JSON and Markdown exports
- Rule-based default mode
- Optional LLM integrations
- Passing unittest suite

In documentary terms, this project is not just an AI campaign generator. It is a miniature marketing operations system: it researches, strategizes, writes, reviews, scores, logs, and explains its own decisions.

