# vigil 🔭

**Uptime monitoring for AI quality.** Proactive testing, drift detection, alerting.

Your AI endpoint is live. But is it still *good*? Vigil sends test queries on a schedule, scores the responses, tracks quality over time, and alerts when it degrades — before your users notice.

```
Today:                                    With Vigil:
──────                                    ──────────
Deploy RAG app                            Deploy + add test queries
Quality degrades over 3 weeks             Quality drop detected in hours
Nobody notices until users complain       Alert: "RAG quality ↓19%"
No idea when it broke or why              History: broke after Oct 15 deploy
```

---

## Table of Contents

- [Why This Exists](#why-this-exists)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Configuration Reference](#configuration-reference)
- [CLI Reference](#cli-reference)
- [Scoring](#scoring)
- [Use on Any Repo / Endpoint](#use-on-any-repo--endpoint)
- [Demo: Catching Real Degradation](#demo-catching-real-degradation)
- [MCP Integration](#mcp-integration)
- [CI/CD Integration](#cicd-integration)
- [Architecture](#architecture)
- [License](#license)

---

## Why This Exists

Every AI observability tool traces your **production traffic** — they tell you what happened *after* it happened. None of them **proactively test** your AI.

| Tool | What it does | What it doesn't do |
|---|---|---|
| **Langfuse** (37K⭐) | Traces LLM calls | Doesn't proactively test quality |
| **Datadog LLM Obs** | Monitors latency/errors | Doesn't score response quality |
| **RAGAS** (10K⭐) | One-shot batch eval | [Crashes on faithfulness](https://github.com/explodinggradients/ragas/issues/1150). No scheduling |
| **Promptfoo** (26K⭐) | Pre-deploy prompt testing | No production monitoring |
| **Vigil** | **Sends test queries on schedule, scores responses, detects drift, alerts** | — |

Vigil is the missing piece: a guard that actively checks if your AI is still healthy.

---

## Quick Start

### 1. Install

```bash
pip install vigil-ai

# Install LLM provider for scoring (pick one):
pip install openai          # for OpenRouter or OpenAI
pip install google-genai    # for Gemini
```

### 2. Set API key

Create a `.env` file in your project root (or export as env var):

```bash
# .env — pick ONE provider for the LLM judge
# OpenRouter (recommended — one key, all models):
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# OR OpenAI directly:
# OPENAI_API_KEY=sk-your-key-here

# OR Google Gemini:
# GOOGLE_API_KEY=your-key-here
```

Vigil auto-detects which key is available. Priority: OpenRouter > OpenAI > Gemini > rule-based (no key).

### 3. Create config

```bash
vigil init
```

This creates `vigil.yaml`. Edit it to point to your AI endpoint and add test queries:

```yaml
name: "My AI App"
endpoint: "http://localhost:8000/api/chat"
response_field: "response"
scorer_model: ""  # auto-detect from API key

tests:
  - name: "basic_test"
    query: "What is your return policy?"
    expect:
      contains: ["30 days", "refund"]
```

### 4. Set baseline (first time)

```bash
vigil baseline
```

This runs all tests and saves the scores as your quality reference point.

### 5. Run quality checks

```bash
vigil run
```

Output:
```
  vigil — 2026-11-03 11:43
  Config: My AI App

    OK  return_policy             1.00  (baseline: 1.00)  +0%
    OK  pricing_details           1.00  (baseline: 1.00)  +0%
    !!  enterprise_vs_pro         0.00  (baseline: 1.00)  -100% DEGRADED

  Overall: 2/3 pass, 1 degraded
  Average score: 0.67 (baseline: 1.00) -33.3%

  !!! QUALITY ALERTS !!!
  !! enterprise_vs_pro: score dropped 100.0% (1.00 -> 0.00)
```

### 6. Continuous monitoring

```bash
vigil watch --every 30          # check every 30 minutes
vigil watch --every 360         # every 6 hours
```

Runs until you `Ctrl+C`. Each cycle: test → score → drift check → alert.

---

## How It Works

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
│ vigil.yaml   │────>│ Runner       │────>│ Scorer       │────>│ Tracker  │
│ (test suite) │     │ (HTTP calls  │     │ (LLM judge   │     │ (SQLite  │
│              │     │  to your app)│     │  scores 0-1) │     │  history)│
└─────────────┘     └──────────────┘     └──────────────┘     └──────────┘
                                                                    │
                                                              ┌─────▼──────┐
                                                              │ Alerter    │
                                                              │ (console + │
                                                              │  webhook)  │
                                                              └────────────┘
```

1. **Define** test queries + expectations in `vigil.yaml`
2. **Run** → Vigil sends each query to your AI endpoint via HTTP
3. **Score** → LLM-as-judge evaluates each response (0.0–1.0)
4. **Track** → Scores saved in SQLite, compared against baseline
5. **Alert** → If quality drops beyond threshold, alerts fire

---

## Configuration Reference

### `vigil.yaml`

```yaml
# Required
endpoint: "http://localhost:8000/api/chat"    # your AI endpoint

# Optional (with defaults)
name: "My App"                 # display name in reports
response_field: "response"     # JSON field containing the AI's answer
alert_threshold: 0.15          # alert if quality drops >15% from baseline
scorer_model: ""               # "" = auto-detect. Or: "gpt-4o-mini", "openai/gpt-4o-mini"
timeout: 30                    # seconds per HTTP request

# Test cases
tests:
  - name: "test_name"          # unique identifier
    query: "Your question"     # sent to the endpoint
    expect:                    # expectations for scoring
      contains: ["keyword1", "keyword2"]   # response must include these
      min_length: 100                       # minimum character count
      contains_numbers: true                # must include numbers
      no_hallucination: true                # no made-up information
      tone: "professional"                  # expected tone
      grounded_in_context: true             # answers must be supported
      language: "en"                        # expected language
```

### Custom request format

By default, vigil sends `{"message": "your query"}`. Override with `body_template`:

```yaml
tests:
  - name: "custom_format"
    query: "Hello"
    body_template: '{"messages": [{"role": "user", "content": "{{query}}"}]}'
    headers:
      Authorization: "Bearer your-token"
    method: "POST"
```

---

## CLI Reference

| Command | What it does |
|---|---|
| `vigil init` | Create a sample `vigil.yaml` in the current directory |
| `vigil run` | Run all tests, score, detect drift, report |
| `vigil watch --every N` | Run tests every N minutes continuously |
| `vigil baseline` | Run tests and set scores as the reference point |
| `vigil history` | Show summary of all runs |
| `vigil history --test NAME` | Show score trend for a specific test |

### Common flags

```bash
vigil run -c path/to/vigil.yaml      # custom config path
vigil run --db path/to/history.db    # custom database path
vigil run --webhook https://hooks.slack.com/xxx   # Slack/Discord alerts
```

---

## Scoring

### LLM-as-Judge (with API key)

Vigil uses an LLM to evaluate each response against your expectations. The judge returns a score from 0.0 to 1.0 with reasoning.

| Provider | Set this env var | Default model |
|---|---|---|
| **OpenRouter** (recommended) | `OPENROUTER_API_KEY` | `openai/gpt-4o-mini` |
| **OpenAI** | `OPENAI_API_KEY` | `gpt-4o-mini` |
| **Gemini** | `GOOGLE_API_KEY` | `gemini-3.8-flash` |

Override the model in `vigil.yaml`:
```yaml
scorer_model: "openai/gpt-4o-mini"        # via OpenRouter
scorer_model: "anthropic/claude-3-haiku"   # Claude via OpenRouter
scorer_model: "gpt-4o-mini"               # direct OpenAI
```

### Rule-Based (no API key)

Without any API key, vigil uses deterministic checks:
- `contains` → keyword presence check
- `min_length` → character count
- `contains_numbers` → regex for digits

Scores are still tracked and drift is still detected — just less nuanced.

---

## Use on Any Repo / Endpoint

Vigil tests your AI **from the outside** via HTTP. It doesn't live inside your codebase.

### Step 1: Know your endpoint

| Your AI app | Endpoint to use |
|---|---|
| FastAPI server | `http://localhost:8000/chat` |
| Deployed on Vercel | `https://my-app.vercel.app/api/ask` |
| AWS Lambda | `https://xyz.execute-api.us-east-1.amazonaws.com/prod/ask` |
| Internal service | `http://internal-service:8080/query` |

### Step 2: Know the response format

If your API returns:
```json
{"response": "Here is the answer..."}
```
Set `response_field: "response"` in `vigil.yaml`.

If it returns:
```json
{"data": {"answer": "Here is..."}}
```
Vigil tries common field names: `response`, `answer`, `content`, `text`, `message`, `output`.

### Step 3: Write test queries

Pick 5-10 queries that cover your app's key use cases. For each, define what a good answer looks like:

```yaml
tests:
  # Simple factual query
  - name: "refund_policy"
    query: "What is the refund policy?"
    expect:
      contains: ["30 days"]

  # Complex reasoning query
  - name: "plan_comparison"
    query: "Compare Pro vs Enterprise plans in detail"
    expect:
      min_length: 100
      contains_numbers: true

  # Edge case
  - name: "unknown_topic"
    query: "Do you offer quantum computing services?"
    expect:
      tone: "helpful"
      no_hallucination: true
```

### Step 4: Run

```bash
# First time — set the baseline
vigil baseline -c vigil.yaml

# After any change (model swap, config update, new deploy):
vigil run -c vigil.yaml

# Continuous monitoring:
vigil watch -c vigil.yaml --every 60
```

---

## Demo: Catching Real Degradation

This demo proves vigil catches quality drops from real production changes — no mocking, no tampering.

### Prerequisites

```bash
# Clone the repo
git clone <repo-url> && cd vigil

# Install
pip install -e ".[openai]"

# Set your OpenRouter key (get one free at https://openrouter.ai/keys)
# Create .env file:
echo "OPENROUTER_API_KEY=sk-or-v1-your-key-here" > .env
```

### Run the automated demo

```bash
python demo/run_demo.py
```

This runs 3 scenarios automatically (~3 minutes):

| Scenario | What happens | Expected result |
|---|---|---|
| 1. **Baseline** | Good model (`openai/gpt-4o-mini`) + full knowledge base | Scores 0.97+ avg — all tests pass |
| 2. **Model swap** | Cheap free model (`liquid/lfm-2.5-2.6b:free`) | Simple tests pass, complex tests degrade |
| 3. **Corrupted docs** | Good model but outdated/vague knowledge base | All tests degrade — no facts to answer with |

### Actual demo output (November 2026)

**Scenario 1 — Baseline (GPT-4o-mini):**
```
  Baseline set:
    return_policy             1.00
    pricing_details           1.00
    business_hours            1.00
    security_certs            0.80
    enterprise_vs_pro         1.00
    support_sla               1.00
```

**Scenario 2 — Free model swap:**
```
    OK  return_policy             1.00  (baseline: 1.00)  +0%
    OK  pricing_details           1.00  (baseline: 1.00)  +0%
    OK  business_hours            1.00  (baseline: 1.00)  +0%
    OK  security_certs            1.00  (baseline: 0.80)  +25%
    !!  enterprise_vs_pro         0.00  (baseline: 1.00)  -100% DEGRADED
    OK  support_sla               1.00  (baseline: 1.00)  +0%

  !!! QUALITY ALERTS !!!
  !! enterprise_vs_pro: score dropped 100.0% (1.00 -> 0.00)
```

The free 2.6B model handles simple factual questions fine but **fails on the complex comparison question** — exactly the kind of nuanced degradation that goes unnoticed in production.

**Scenario 3 — Corrupted knowledge base:**
```
    !!  return_policy             0.00  (baseline: 1.00)  -100% DEGRADED
    !!  pricing_details           0.00  (baseline: 1.00)  -100% DEGRADED
    ... (all 6 tests degraded)

  !!! QUALITY ALERTS !!!
  !! return_policy: score dropped 100.0% (1.00 -> 0.00)
  !! pricing_details: score dropped 100.0% (1.00 -> 0.00)
  ...
```

### Run each scenario manually

**Terminal 1 — Start the RAG app:**

```bash
# Good model + good docs (baseline)
python demo/rag_app.py

# Cheap model (cost-cutting simulation)
python demo/rag_app.py --model liquid/lfm-2.5-2.6b:free

# Good model + corrupted docs (stale index simulation)
python demo/rag_app.py --corrupt-context
```

**Terminal 2 — Run vigil:**

```bash
# Set baseline (first time, with good model running)
vigil baseline -c demo/vigil.yaml --db demo/history.db

# Switch the RAG app to cheap model (Ctrl+C terminal 1, restart with --model flag)
# Then run vigil again:
vigil run -c demo/vigil.yaml --db demo/history.db

# View score history:
vigil history --db demo/history.db

# View specific test trend:
vigil history --test enterprise_vs_pro --db demo/history.db
```

### What the demo teaches

| Production failure | How vigil catches it |
|---|---|
| Team swaps to cheaper model to save costs | Complex queries fail, simple ones pass. Vigil alerts on the specific tests that degraded |
| Stale/corrupted vector index deployed | All queries return vague answers. Vigil detects all scores dropped vs baseline |
| Model provider silently updates model | Scores drift over time. `vigil watch` catches the trend |

---

## MCP Integration

Expose vigil as tools for Claude Code, Claude Desktop, or Cursor.

### Setup

```bash
# Claude Code
claude mcp add vigil -- python -m vigil_ai

# Claude Desktop — add to claude_desktop_config.json:
{
  "mcpServers": {
    "vigil": {
      "command": "python",
      "args": ["-m", "vigil_ai"],
      "env": {
        "OPENROUTER_API_KEY": "your-key"
      }
    }
  }
}
```

### Available tools

| Tool | What you ask Claude |
|---|---|
| `vigil_run` | "Check my AI quality" / "Run quality tests" |
| `vigil_history` | "Show quality history" / "How has quality trended?" |
| `vigil_baseline` | "Set a new quality baseline" |
| `vigil_init` | "Create a vigil config for my app" |

---

## CI/CD Integration

### GitHub Actions

```yaml
# .github/workflows/vigil.yml
name: AI Quality Check
on:
  schedule:
    - cron: '0 */6 * * *'     # every 6 hours
  push:
    branches: [main]           # also on deploy

jobs:
  vigil:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install vigil-ai openai
      - run: vigil run -c vigil.yaml
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

Vigil exits with code 1 when alerts fire — the CI job fails, notifying your team.

### Cron (Linux/Mac)

```bash
# Check every 6 hours
0 */6 * * * cd /path/to/project && OPENROUTER_API_KEY=your-key vigil run -c vigil.yaml 2>&1 | tee -a /var/log/vigil.log
```

---

## Architecture

```
vigil/
├── src/vigil_ai/
│   ├── config.py         # YAML config parser
│   ├── runner.py         # HTTP test runner
│   ├── scorer.py         # LLM-as-judge (OpenRouter/OpenAI/Gemini) + rule-based fallback
│   ├── tracker.py        # SQLite history + drift detection + baselines
│   ├── alerter.py        # Console + webhook (Slack/Discord) alerts
│   ├── cli.py            # CLI: run, watch, baseline, history, init
│   └── mcp_server.py     # MCP server for Claude Code / Cursor
├── demo/
│   ├── rag_app.py        # Demo RAG app (good/cheap model + good/corrupted docs)
│   ├── run_demo.py       # Automated 3-scenario demo
│   └── vigil.yaml        # Demo test suite
├── tests/
│   └── test_core.py      # 16 tests (all mock-based, zero API calls)
└── .env                  # API keys (gitignored, never committed)
```

- **Zero infrastructure** — SQLite for history, YAML for config. No server needed
- **Any AI endpoint** — just needs HTTP. Works with any framework
- **Provider-agnostic** — OpenRouter, OpenAI, Gemini, or no LLM at all (rule-based)
- **Minimal dependencies** — `pyyaml` + one LLM SDK (optional)

---

## License

MIT — Virat Srivastava
