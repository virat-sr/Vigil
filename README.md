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

This project uses [uv](https://docs.astral.sh/uv/) for Python, virtual environments and dependencies.

### 1. Install uv (once per machine)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # or: brew install uv
```

### 2. Create the environment

```bash
git clone <repo-url> vigil && cd vigil
uv sync --all-extras        # creates .venv/ (Python 3.13 per .python-version) + installs everything
```

`uv sync` installs vigil in editable mode plus `pytest`. `--all-extras` adds the `openai`, `gemini` and `mcp` SDKs.
Only need one provider? Use `uv sync --extra openai` (also covers OpenRouter) or `uv sync --extra gemini`.

Run any command inside the environment with `uv run …` (no activation needed), e.g. `uv run vigil --help`.
If you prefer activating it: `source .venv/bin/activate`, then just `vigil …`.

### 3. Set API key (optional)

```bash
cp .env.example .env        # .env is gitignored — never committed
```

Fill in **one** key in `.env` (priority: OpenRouter > OpenAI > Gemini). Keep comments on their own lines:

```bash
OPENROUTER_API_KEY=sk-or-v1-your-key
```

No key? Vigil falls back to free rule-based scoring. `.env` is read from the **current directory**, so run commands from the repo root.

### 4. Create config

```bash
uv run vigil init    # creates vigil.yaml
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

### 5. Set baseline + start monitoring

```bash
uv run vigil baseline                # set quality reference point
uv run vigil watch --every 360       # check every 6 hours, forever
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

Prefix each command with `uv run` (e.g. `uv run vigil run`), or `source .venv/bin/activate` once and use them as-is.

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
uv run vigil dashboard --db vigil_history.db
# Open http://localhost:9090
```

Dark-themed visual dashboard showing:
- **Health banner** — overall score, pass/degraded/failed counts
- **Quality over time** — line chart per test with baseline reference
- **Test results table** — score, drift %, status, reasoning
- **Score distribution** — horizontal bar chart
- **Run history** — color-coded pills per run

---

## Demo: Step-by-Step (Record This for Video)

The demo runs a tiny "Acme Corp" support bot on `http://localhost:8500`, sets a quality baseline,
then breaks the bot's knowledge base and shows vigil catching it. You need **two terminals**, both opened in the repo root.

Two ways to run the bot:

| | Bot | API key | Scoring |
|---|---|---|---|
| **Path A — real LLM** (best for video) | `demo/rag_app.py` — real LLM answering from docs | Required (`.env`) | LLM-as-judge |
| **Path B — offline** | `examples/mock_api_server.py` — canned answers | Not needed | Rule-based (if `.env` has no key) |

### Step 0: One-time setup

```bash
cd vigil
uv sync --all-extras          # create .venv and install vigil + openai/gemini SDKs + pytest
cp .env.example .env          # then edit .env and paste your key (Path A only)
uv run pytest -q              # optional sanity check — expect "16 passed"
rm -f demo/history.db         # start the demo with a clean history
```

### Step 1: Start the AI app with the GOOD knowledge base — Terminal 2

```bash
uv run python demo/rag_app.py                    # Path A (real LLM)
# or
uv run python examples/mock_api_server.py        # Path B (offline)
```

Path A prints:
```
  Acme Corp RAG App
  Provider: openrouter
  Model:    openai/gpt-4o-mini
  Context:  Full knowledge base
  Running:  http://localhost:8500
```

Leave it running.

### Step 2: Set the quality baseline — Terminal 1

```bash
uv run vigil baseline -c demo/vigil.yaml --db demo/history.db
```

All tests should score high (≈0.80–1.00):
```
  Baseline set:
    return_policy             1.00
    pricing_details           1.00
    business_hours            1.00
    security_certs            1.00
    enterprise_features       1.00
    support_sla               1.00
```

**This is your quality reference point — "this is what good looks like."**

### Step 3: Verify quality is stable — Terminal 1

```bash
uv run vigil run -c demo/vigil.yaml --db demo/history.db
```

Scores match the baseline. No alerts. **Quality is stable.**

### Step 4: Corrupt the knowledge base (the key moment) — Terminal 2

Press `Ctrl+C` to stop the app, then restart it with bad data:

```bash
uv run python demo/rag_app.py --corrupt-context            # Path A
# or
uv run python examples/mock_api_server.py --degrade        # Path B
```

Path A prints `Context:  CORRUPTED` — **this is the change.**
It simulates someone editing the knowledge-base docs: old prices, shorter return window, vague security info. No code change. No deploy.

### Step 5: Run vigil — watch it catch the degradation — Terminal 1

```bash
uv run vigil run -c demo/vigil.yaml --db demo/history.db
```

You should see:
```
    !!  return_policy             0.29  (baseline: 1.00)  -71% DEGRADED
    !!  pricing_details           0.29  (baseline: 1.00)  -71% DEGRADED
    ...

  !!! QUALITY ALERTS !!!
  !! return_policy: score dropped 71.0% (1.00 -> 0.29)
  !! pricing_details: score dropped 71.0% (1.00 -> 0.29)
```

(Exact numbers vary with the judge model; any drop beyond 15% raises an alert.)
**Vigil caught it.** No code changed. No deploy happened. The data changed and vigil detected the quality drop.

### Step 6: Fix the data and verify recovery

Terminal 2 — `Ctrl+C`, then restart with good data:

```bash
uv run python demo/rag_app.py                    # Path A
# or
uv run python examples/mock_api_server.py        # Path B
```

Terminal 1:

```bash
uv run vigil run -c demo/vigil.yaml --db demo/history.db
```

Scores recover to baseline. **Full cycle: healthy → degraded → detected → fixed → healthy.**

### Step 7: Check history — Terminal 1

```bash
uv run vigil history --db demo/history.db
uv run vigil history --db demo/history.db --test pricing_details
```

### Step 8: View the dashboard — Terminal 1

```bash
uv run vigil dashboard --db demo/history.db
```

Open **http://localhost:9090** (stop with `Ctrl+C`). You'll see the score chart dropping and recovering,
red alerts on degraded tests, and run history good → good → bad → good. Click any run for its details.

Finally, stop the app in Terminal 2 with `Ctrl+C`.

### One-command variant (OpenRouter key required)

```bash
uv run python demo/run_demo.py
```

Runs three scenarios automatically — good model baseline, swap to a tiny free model, corrupted docs — and prints the history.
It uses OpenRouter model IDs, so it needs `OPENROUTER_API_KEY` in `.env`. Results go to `demo/demo_history.db`
(view with `uv run vigil dashboard --db demo/demo_history.db`).

### Troubleshooting

| Symptom | Fix |
|---|---|
| `Connection refused` / all tests `[ERR]` | The app in Terminal 2 isn't running, or is on a port other than 8500 |
| `Address already in use` | Something else is on 8500 — stop it, or `lsof -i :8500` to find it |
| `RuntimeError: Set OPENROUTER_API_KEY...` | `.env` missing or empty — Path A needs a key (or use Path B) |
| Scoring says `rule-based (no API key)` | Expected for Path B; for Path A, run commands from the repo root so `.env` is found |
| Old runs show up in history/dashboard | `rm -f demo/history.db` and start over from Step 1 |

---

## Why Not Just Use LangSmith / Langfuse / Braintrust?

**For most teams, you should.** They're better products with bigger teams and polished dashboards.

Vigil is not a competitor. It's a different tool for a different job:

> **LangSmith = comprehensive health checkup at the hospital**
> **Vigil = a thermometer you check every morning at home**

### When the thermometer is enough

| Situation | LangSmith/Langfuse | Vigil |
|---|---|---|
| **Setup time** | Hours (install SDK, instrument code, configure) | **5 minutes (YAML + CLI)** |
| **Code changes needed** | Yes — wrap LLM calls with their tracer | **None — tests from outside via HTTP** |
| **Monitor an app you don't own** | Can't install SDK in someone else's code | **Just point at the URL** |
| **Pre-launch (no users yet)** | Needs production traffic to analyze | **Sends its own test queries** |
| **Cost** | Free tier → $39-249/month | **~$0.90/month** |
| **Low-traffic features** | Not enough traffic for statistical analysis | **Tests every category every run** |

### When you need the hospital

| Situation | Use LangSmith/Langfuse |
|---|---|
| Full production observability | ✅ They trace every call |
| Debug specific user conversations | ✅ They have trace viewers |
| Enterprise (SOC2, RBAC, audit logs) | ✅ They have compliance features |
| Analyze real user query patterns | ✅ They see actual traffic |

### Best combo

```
Vigil ($0.90/month)      →  Catches data-driven quality drops proactively
+ Langfuse (free tier)   →  Traces production calls for debugging when vigil alerts

Total: $0.90/month. Covers both proactive monitoring and reactive debugging.
```

**Start with the thermometer. Go to the hospital when the thermometer shows a fever.**

---

## CI/CD Integration

```yaml
# .github/workflows/vigil.yml
# Key: triggered by SCHEDULE, not push — catches data changes between deploys
name: AI Quality Monitor
on:
  schedule:
    - cron: '0 */6 * * *'

jobs:
  vigil:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --extra openai
      - run: uv run vigil run
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

---

## MCP Integration

```bash
# Claude Code
claude mcp add vigil -- uv run --directory /absolute/path/to/vigil python -m vigil_ai

# Then ask Claude:
# "Check my AI quality"
# "Show quality history for pricing"
# "Set a new baseline"
```

---

## Architecture

```
vigil/
├── src/vigil_ai/
│   ├── config.py          # YAML config parser
│   ├── runner.py          # HTTP test runner (any endpoint)
│   ├── scorer.py          # LLM judge (OpenRouter/OpenAI/Gemini) + rule-based
│   ├── tracker.py         # SQLite: history, baselines, drift detection
│   ├── alerter.py         # Console + webhook (Slack/Discord)
│   ├── dashboard.py       # Visual dashboard (Chart.js, dark theme)
│   ├── cli.py             # CLI: run, watch, baseline, history, dashboard, init
│   └── mcp_server.py      # MCP server for Claude Code / Cursor
├── demo/                  # RAG app with good/corrupted data modes
├── examples/              # Offline mock API server (no key needed)
├── tests/                 # 16 tests (mock-based, zero API calls) — `uv run pytest`
├── pyproject.toml         # deps + extras; uv.lock pins exact versions
├── .python-version        # Python version uv uses for .venv
└── .env.example           # copy to .env and add your API key
```

- **Zero infrastructure** — SQLite + YAML. No server, no database, no cloud
- **Any endpoint** — just HTTP. No SDK integration in your app
- **5-minute setup** — `vigil init` → edit YAML → `vigil watch`
- **~$0.90/month** — or $0 with rule-based scoring (no API key)

---

## License

MIT — Virat Srivastava
