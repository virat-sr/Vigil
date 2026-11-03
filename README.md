# vigil 🔭

**Scheduled quality monitor for AI systems where data changes without pipelines.**

CI evals catch code bugs. Reindex hooks catch reindex bugs. But what catches the support agent who edits a Confluence article, the partner whose API changes format, or the five different teams updating five different data sources your RAG pulls from?

**Vigil does.** It tests your live AI on a schedule — not triggered by deploys or pipelines, but by time.

---

## The Problem

Every data change that degrades AI quality doesn't come with a pipeline you can hook evals into.

### "Just add evals to the pipeline" — works when there IS a pipeline

| Data change | Pipeline exists? | Can you add eval hook? |
|---|---|---|
| Code deploy | ✅ CI/CD | ✅ Yes — add eval step |
| Automated reindex | ✅ Cron/Airflow | ✅ Yes — add eval step after reindex |

**Vigil is not for these.** Your CI handles them fine.

### Vigil is for when there is NO pipeline

| Data change | Pipeline exists? | Can you add eval hook? |
|---|---|---|
| Support agent edits FAQ article in Confluence | ❌ It's a CMS. No pipeline | ❌ **No** |
| Content writer updates pricing page in Notion | ❌ It's a wiki. No pipeline | ❌ **No** |
| Legal team revises refund policy in SharePoint | ❌ It's a doc. No pipeline | ❌ **No** |
| Partner API changes response format silently | ❌ Not your system | ❌ **No** |
| Scraped website updates their layout | ❌ Not your system | ❌ **No** |
| 5 teams update 5 data sources on different schedules | ❌ No unified pipeline | ❌ **No** |
| Embedding quality degrades as index grows 10x over 3 months | ❌ No single event caused it | ❌ **No** |
| Peak traffic — self-hosted model batches aggressively | ❌ Load-dependent, time-of-day | ❌ **No** |

**There is no deploy. There is no reindex. There is no pipeline. A human edited a page in a CMS. Your RAG scraped it. Your AI now gives wrong answers. Where do you put the eval hook?**

### The gap

```
Code changes     ──CI──→        evals run  ✅  (you handle this)
Automated reindex ──pipeline──→  evals run  ✅  (you can handle this)
CMS edits         ──nothing──→   ???        ❌  ← vigil
External data     ──nothing──→   ???        ❌  ← vigil
Multiple sources  ──nothing──→   ???        ❌  ← vigil
Gradual drift     ──nothing──→   ???        ❌  ← vigil
```

**Vigil runs on a timer, not a trigger.** Every 6 hours, it sends test queries to your live endpoint and checks if the answers are still correct — regardless of what changed or didn't change.

---

## Quick Start

### 1. Install

```bash
pip install vigil-ai openai    # openai SDK needed for OpenRouter/OpenAI scoring
```

### 2. Set API key

```bash
# .env (gitignored — never committed)
OPENROUTER_API_KEY=sk-or-v1-your-key    # get free at openrouter.ai/keys
```

### 3. Create config

```bash
vigil init    # creates vigil.yaml
```

Edit `vigil.yaml` — point to your production endpoint, add queries your real users ask:

```yaml
name: "Customer Support RAG"
endpoint: "https://my-app.com/api/chat"
response_field: "response"
alert_threshold: 0.15

tests:
  - name: "refund_policy"
    query: "What is your refund policy?"
    expect:
      contains: ["30 days", "full refund"]

  - name: "pricing"
    query: "How much does the Pro plan cost?"
    expect:
      contains: ["49"]
      contains_numbers: true

  - name: "hours"
    query: "When are you open?"
    expect:
      contains: ["Monday", "Friday"]
```

### 4. Set baseline + start monitoring

```bash
vigil baseline                # set quality reference point
vigil watch --every 360       # check every 6 hours, forever
```

When quality drops:
```
  !! refund_policy    0.40  (baseline: 1.00)  -60% DEGRADED
  !! pricing          0.00  (baseline: 1.00)  -100% DEGRADED

  !!! QUALITY ALERTS !!!
  !! refund_policy: score dropped 60.0% (1.00 -> 0.40)
  !! pricing: score dropped 100.0% (1.00 -> 0.00)
```

You investigate → find out the content team edited the pricing page yesterday. Fix the doc. Quality recovers. **Users never noticed.**

---

## Real-World Examples

### Example 1: Support Agent Edits Confluence Article

**Scenario:** E-commerce company. AI chatbot answers customer questions using RAG over Confluence docs.

```
Before:
  Confluence article: "Returns accepted within 30 days for full refund.
                       Items must be unused, original packaging."
  Vigil baseline: refund_policy = 1.00 ✅

What happened:
  Support agent edits the article to: "Please see our returns page for current policy."
  They thought they were reducing duplicate content.
  No deploy. No reindex. No pipeline. Just a Confluence edit.
  RAG's live crawler picks it up within hours.

Next vigil run (6 hours later):
  refund_policy = 0.20 ❌
  Alert: "refund_policy dropped 80% — response missing '30 days', 'full refund'"

Resolution:
  Team finds the Confluence edit, reverts it. Quality restored.
  Total downtime: 6 hours (instead of days).

Without vigil:
  Customers get vague refund answers for 5 days.
  3 support tickets escalated. CSAT drops.
  Nobody connects the dots to the Confluence edit.
```

**Why CI can't catch this:** There is no pipeline between "agent clicks Save in Confluence" and "AI serves wrong answers." You can't add eval hooks to Confluence page saves.

### Example 2: Partner API Changes Response Format

**Scenario:** Travel booking AI that pulls hotel availability from a partner API.

```
Before:
  Partner API returns: {"price": "$199", "available": true}
  AI answers: "The hotel is $199/night and available."
  Vigil baseline: hotel_pricing = 1.00 ✅

What happened:
  Partner updates their API. Now returns: {"rate": "199.00", "status": "OPEN"}
  Different field names. Different format. No notification to you.
  Your parser still works (no crash) but extracts wrong data.
  No deploy. Not your system. No pipeline to hook into.

Next vigil run:
  hotel_pricing = 0.10 ❌
  Alert: "hotel_pricing dropped 90% — response missing price info"

Resolution:
  Team updates parser for new format. Fixes in hours.

Without vigil:
  AI shows "price unavailable" for 2 weeks.
  Users book through competitors. Revenue lost.
```

**Why CI can't catch this:** The partner changed THEIR system. You have no pipeline, no trigger, no webhook for "partner updated their API format."

### Example 3: Five Teams, Five Data Sources, No Unified Pipeline

**Scenario:** Enterprise internal AI assistant. RAG pulls from 5 sources.

```
Data sources:
  1. Confluence (HR policies)     — edited by HR team
  2. Zendesk (support articles)   — edited by support team
  3. Product wiki (feature docs)  — edited by product team
  4. API docs (auto-generated)    — updated by CI
  5. Slack archives (discussions) — continuously updated

What happened:
  - HR rewrote the PTO policy in Confluence (Tuesday)
  - Support archived 50 old articles in Zendesk (Wednesday)
  - Product renamed a feature in the wiki (Thursday)
  None of these teams coordinated. None triggered a deploy.

Vigil run Thursday evening:
  pto_policy = 0.30 ❌ (HR rewrote it, new wording doesn't match expectations)
  feature_question = 0.00 ❌ (renamed feature, old name not found)
  support_process = 0.50 ❌ (archived articles were the RAG source for this)

Resolution:
  AI team updates embeddings for changed docs. Adjusts vigil.yaml expectations.

Without vigil:
  Employees get wrong PTO info, outdated feature names, broken support answers.
  Nobody realizes 3 different edits by 3 different teams caused 3 different failures.
```

**Why CI can't catch this:** You'd need eval hooks in Confluence AND Zendesk AND the wiki AND Slack. Across 4 teams who don't know your AI exists. That's not realistic.

### Example 4: Gradual Drift — No Single Event

**Scenario:** Legal AI that answers contract questions from a 50K document index.

```
Month 1:  Index has 50K docs. Retrieval precision is excellent.
          Vigil baseline: avg 0.94 ✅

Month 2:  Index grows to 75K docs. Slightly more noise in retrieval.
          Vigil: avg 0.91 (within threshold, no alert)

Month 3:  Index at 100K docs. Similar docs compete for retrieval slots.
          Vigil: avg 0.85 ⚠️ Alert: "avg dropped 9.6% from baseline"

Month 4:  Index at 120K. Retrieval regularly pulls wrong contract type.
          Vigil: avg 0.72 ❌ Alert: "contract_type dropped 28%"

Resolution:
  Team implements better chunking strategy and metadata filtering.

Without vigil:
  Lawyers get wrong contract clauses. Nobody notices the slow degradation
  because each week is only 1-2% worse. After 4 months: 22% total drop.
  No single event caused it. No deploy to blame. No CI run to catch it.
```

**Why CI can't catch this:** There is no event to trigger evals. Quality degrades 1% per week. Each individual change is invisible. Only the trend line reveals it — and CI doesn't track trends across runs.

---

## How It Works

```
vigil.yaml          →  Runner            →  Scorer           →  Tracker
(your test queries)    (HTTP calls to       (LLM-as-judge       (SQLite: history,
                        production)          scores 0.0-1.0)     baselines, drift)
                                                                      │
                                                                 Alerter
                                                                 (console + Slack)
```

1. **Define** 5-10 queries your real users ask, with expected keywords/facts
2. **Baseline** → vigil runs them, saves scores as reference
3. **Watch** → vigil re-runs every N hours, compares to baseline
4. **Alert** → if any test drops beyond threshold, you get notified

---

## CLI Reference

```bash
vigil init                         # create vigil.yaml template
vigil baseline                     # run tests, set as quality reference
vigil run                          # one-shot quality check
vigil watch --every 360            # check every 6 hours continuously
vigil history                      # show all runs summary
vigil history --test pricing       # show one test's trend
vigil dashboard                    # open visual dashboard in browser
```

### Flags

```bash
vigil run -c path/to/vigil.yaml         # custom config
vigil run --db path/to/history.db        # custom database
vigil run --webhook https://hooks.slack.com/xxx  # Slack alerts
vigil dashboard --port 9090              # dashboard port
```

---

## Configuration (`vigil.yaml`)

```yaml
# Required
endpoint: "https://my-app.com/api/chat"

# Optional
name: "My App"
response_field: "response"     # JSON field with the AI's answer
alert_threshold: 0.15          # alert if >15% drop from baseline
scorer_model: ""               # "" = auto-detect from API key
timeout: 30                    # seconds per request

tests:
  - name: "test_name"
    query: "A real user question"
    expect:
      contains: ["expected", "keywords"]    # must include these
      min_length: 100                        # minimum response length
      contains_numbers: true                 # must include numbers
      no_hallucination: true                 # no made-up info
      tone: "professional"                   # expected tone
```

### Custom request format

```yaml
tests:
  - name: "custom"
    query: "Hello"
    body_template: '{"messages": [{"role": "user", "content": "{{query}}"}]}'
    headers:
      Authorization: "Bearer token"
```

---

## Scoring

### With API key (LLM-as-judge)

| Provider | Env var | Default model | Monthly cost (~4 runs/day, 6 tests) |
|---|---|---|---|
| **OpenRouter** | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` | ~$0.90 |
| **OpenAI** | `OPENAI_API_KEY` | `gpt-4o-mini` | ~$0.90 |
| **Gemini** | `GOOGLE_API_KEY` | `gemini-3.8-flash` | ~$0.50 |

### Without API key (rule-based, free)

Checks `contains` keywords, `min_length`, `contains_numbers` deterministically. Less nuanced but $0 cost. Still tracks drift.

---

## Dashboard

```bash
vigil dashboard --db vigil_history.db
# Open http://localhost:9090
```

Dark-themed visual dashboard showing:
- **Health banner** — overall score, pass/degraded/failed counts
- **Quality over time** — line chart per test with baseline reference
- **Test results table** — score, drift %, status, reasoning
- **Score distribution** — horizontal bar chart
- **Run history** — color-coded pills per run

---

## Demo: Try It Yourself

```bash
git clone <repo> && cd vigil
pip install -e ".[openai]"
echo "OPENROUTER_API_KEY=your-key" > .env

# Automated demo (3 scenarios, ~3 min)
python demo/run_demo.py

# Visual dashboard after demo
vigil dashboard --db demo/demo_history.db
```

---

## CI/CD Integration

```yaml
# .github/workflows/vigil.yml — runs on schedule, NOT on deploy
name: AI Quality Monitor
on:
  schedule:
    - cron: '0 */6 * * *'    # every 6 hours — catches data changes between deploys

jobs:
  vigil:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install vigil-ai openai
      - run: vigil run
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

**Key: triggered by `schedule`, not `push`.** That's the whole point — catching what deploys don't trigger.

---

## MCP Integration

```bash
# Claude Code
claude mcp add vigil -- python -m vigil_ai

# Ask Claude: "Check my AI quality" / "Show quality history"
```

---

## vigil vs Eval Frameworks — When to Use What

| Scenario | Best tool | Why |
|---|---|---|
| You push code, want to test before deploy | **CI evals (Promptfoo, DeepEval)** | Triggered by deploy, tests your code changes |
| You run a reindex, want to verify after | **Eval hook in reindex pipeline** | Add eval step after reindex completes |
| Content team edits docs in CMS | **vigil** | No pipeline exists to hook into |
| External data source changes | **vigil** | Not your system, no trigger available |
| Multiple teams update data independently | **vigil** | No unified pipeline across teams |
| Slow quality drift over months | **vigil** | No single event to trigger evals, only trend reveals it |
| You want to monitor production 24/7 | **vigil** | Runs on schedule regardless of what changed |

| | CI Evals (Promptfoo, DeepEval) | vigil |
|---|---|---|
| **Triggered by** | Code deploys / pipeline hooks | **Time (every N hours)** |
| **Catches** | Code bugs, model changes | **Data bugs, CMS edits, external changes, drift** |
| **Requires** | Pipeline to hook into | **Just an HTTP endpoint** |
| **Tracks trends** | No (point-in-time) | **Yes (baseline + drift detection)** |
| **Cost** | Free | ~$0.90/month |

**They're complementary.** CI evals for what you control. Vigil for what you don't.
| **Use when** | You change prompts/models | **Data changes without deploys** |

**They're complementary, not competing.** Use CI evals for code changes. Use vigil for everything else.

---

## Architecture

```
vigil/
├── src/vigil_ai/
│   ├── config.py          # YAML config parser
│   ├── runner.py          # HTTP test runner
│   ├── scorer.py          # LLM judge (OpenRouter/OpenAI/Gemini) + rule-based
│   ├── tracker.py         # SQLite history + baselines + drift detection
│   ├── alerter.py         # Console + webhook alerts
│   ├── dashboard.py       # Visual dashboard (Chart.js)
│   ├── cli.py             # CLI: run, watch, baseline, history, dashboard, init
│   └── mcp_server.py      # MCP server for Claude Code / Cursor
├── demo/                  # RAG app demo with degradation scenarios
└── tests/                 # 16 tests (mock-based, zero API calls)
```

- **Zero infrastructure** — SQLite + YAML. No server, no database, no cloud
- **Any endpoint** — just HTTP. Works with any AI framework
- **5-minute setup** — `vigil init` → edit YAML → `vigil watch`

---

## License

MIT — Virat Srivastava
