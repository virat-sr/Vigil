# vigil 🔭

**Uptime monitoring for AI quality.** Proactive testing, drift detection, alerting.

Your AI endpoint is live. But is it still *good*? Vigil sends test queries on a schedule, scores the responses, tracks quality over time, and alerts you when it degrades — before your users notice.

```
Today:                                    With Vigil:
──────                                    ──────────
Deploy RAG app                            Deploy + add 10 test queries
Quality degrades over 3 weeks             Quality drop detected in hours
Nobody notices until users complain       Alert: "RAG quality ↓12%"
No idea when it broke or why              Dashboard: broke after Oct 15 deploy
```

## Why This Exists

Every AI observability tool (Langfuse, Datadog, Braintrust) traces your **production traffic** — they tell you what happened *after* it happened. None of them **proactively test** your AI to catch problems *before* users do.

- **Langfuse** (37K⭐) → traces calls. Doesn't proactively test.
- **Datadog LLM Obs** → monitors latency/errors. Doesn't score quality.
- **RAGAS** (10K⭐) → one-shot eval. [Crashes on faithfulness](https://github.com/explodinggradients/ragas/issues/1150). No scheduling.
- **Promptfoo** (26K⭐) → pre-deploy prompt testing. No production monitoring.

**Vigil is the missing piece:** a guard that actively checks if your AI is still healthy.

## Install

```bash
pip install vigil-ai
```

## Quick Start (Any Repo)

```bash
# 1. Create config
vigil init

# 2. Edit vigil.yaml — point to your AI endpoint, add test queries
# 3. Run
vigil run
```

That's it. Three commands.

## Usage

### One-Shot Run
```bash
vigil run                              # test + score + alert
vigil run --webhook https://hooks.slack.com/xxx  # + Slack alerts
```

### Continuous Monitoring (Watch Mode)
```bash
vigil watch --every 30                 # check every 30 minutes
vigil watch --every 360 --webhook $SLACK  # every 6 hours + Slack
```

### Baseline & History
```bash
vigil baseline                         # set current quality as baseline
vigil history                          # show all runs
vigil history --test return_policy     # show one test's trend
```

### CI/CD (GitHub Actions)
```yaml
on:
  schedule:
    - cron: '0 */6 * * *'
jobs:
  vigil:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install vigil-ai
      - run: vigil run
        env:
          GOOGLE_API_KEY: ${{ secrets.GOOGLE_API_KEY }}
```

## Configuration (`vigil.yaml`)

```yaml
name: "My RAG App"
endpoint: "https://my-app.com/api/chat"
response_field: "response"        # JSON field containing the AI answer
alert_threshold: 0.15             # alert if quality drops >15%
scorer_model: "gemini-3.8-flash"  # LLM judge (set GOOGLE_API_KEY)

tests:
  - name: "refund_policy"
    query: "What is your refund policy?"
    expect:
      contains: ["30 days", "full refund"]
      tone: "professional"

  - name: "pricing_comparison"
    query: "Compare Pro and Enterprise plans"
    expect:
      min_length: 100
      contains_numbers: true
      grounded_in_context: true

  - name: "edge_case_german"
    query: "Was ist die Rückgabefrist?"
    expect:
      language: "de"
      contains: ["30 Tage"]
```

### Custom Request Format

```yaml
# OpenAI-compatible API
endpoint: "https://api.example.com/v1/chat/completions"
tests:
  - name: "test1"
    query: "Hello"
    body_template: '{"messages": [{"role": "user", "content": "{{query}}"}]}'
    headers:
      Authorization: "Bearer sk-xxx"
```

## Output

```
  vigil — 2026-11-03 10:24
  Config: My RAG App

    OK  refund_policy             0.95  (baseline: 0.94)  +1%
    OK  pricing_comparison        0.88  (baseline: 0.91)  -3%
    !!  edge_case_german          0.72  (baseline: 0.89)  -19% DEGRADED
    OK  agent_tool_use            0.90  (baseline: 0.88)  +2%

  Overall: 3/4 pass, 1 degraded, 0 failed
  Average score: 0.86 (baseline: 0.91) -5.5%

  !!! QUALITY ALERTS !!!
  !! edge_case_german: score dropped 19.1% (0.89 -> 0.72)
```

## How It Works

1. **Define** test queries + expectations in `vigil.yaml`
2. **Run** → Vigil calls your AI endpoint with each test query
3. **Score** → LLM-as-judge (Gemini) evaluates response quality 0.0-1.0
4. **Track** → Scores stored in SQLite, compared against baseline
5. **Alert** → If quality drops beyond threshold, alerts fire (console + webhook)

Works **without an API key** too — falls back to rule-based scoring (keyword matching, length checks).

## How to Use on Any Repo

Vigil tests your AI **from the outside** via HTTP. It doesn't need to be inside your codebase.

| Your AI App | Vigil Config |
|---|---|
| FastAPI RAG server | `endpoint: "http://localhost:8000/chat"` |
| Deployed on Vercel | `endpoint: "https://my-app.vercel.app/api/ask"` |
| OpenAI-compatible API | `endpoint: "..." + body_template with messages format` |
| Internal service | `endpoint: "http://internal:8080/query"` |

Just point `vigil.yaml` at any HTTP endpoint that accepts a query and returns text.

## Scoring

| Mode | When | How |
|---|---|---|
| **LLM-as-judge** | `GOOGLE_API_KEY` is set | Gemini scores responses against expectations (0.0-1.0) |
| **Rule-based** | No API key | Checks keywords, length, numbers deterministically |

Both modes track history and detect drift.

## Try It: Real Degradation Demo

This demo proves vigil catches quality drops from real production changes — no mocking, no tampering.

```bash
# Prerequisites
export GOOGLE_API_KEY=your_key
pip install vigil-ai google-genai

# Run the full demo (3 scenarios, ~2 minutes)
python demo/run_demo.py
```

**What happens:**

| Scenario | What changes | What vigil detects |
|---|---|---|
| 1. Baseline | Good model (`gemini-3.8-flash`) + full docs | Sets baseline scores (0.85-1.0) |
| 2. Model swap | Cheap model (`gemini-flash-lite-latest`) | Quality drop on detail-heavy queries |
| 3. Bad docs | Good model but corrupted knowledge base | Severe drop — answers become vague |

**Or test each scenario manually:**

```bash
# Terminal 1: Start the RAG app
python demo/rag_app.py                                    # Good model + good docs
python demo/rag_app.py --model gemini-flash-lite-latest   # Cheap model
python demo/rag_app.py --corrupt-context                  # Bad docs

# Terminal 2: Run vigil
vigil baseline -c demo/vigil.yaml --db demo/history.db    # Set baseline (first time)
vigil run -c demo/vigil.yaml --db demo/history.db         # Check quality
vigil history --db demo/history.db                        # View trends
```

**This is the real test** — not synthetic failures, but the exact scenario that happens when someone swaps a model to save costs or deploys with stale data.

## MCP Integration

Expose vigil as an MCP tool for Claude Code, Claude Desktop, or Cursor:

```bash
# Add to Claude Code
claude mcp add vigil -- python -m vigil_ai

# Then ask Claude:
# "Check my AI quality"
# "Show quality history"
# "Set a new baseline"
```

## Architecture

- **Zero infrastructure** — SQLite for history, YAML for config. No database server needed
- **Any AI endpoint** — just needs HTTP. Not tied to LangChain, LlamaIndex, or any framework
- **Minimal dependencies** — `pyyaml` + `google-genai`

## License

MIT
