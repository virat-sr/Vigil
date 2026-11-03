# vigil 🔭

**Scheduled quality monitor for AI systems where data changes without deploys.**

Your CI evals pass on every deploy. But your AI's quality depends on more than code — it depends on **data that changes without anyone deploying anything.** Vigil catches what CI can't: quality degradation caused by data changes, not code changes.

---

## The Problem CI Evals Can't Solve

CI evals are triggered by **code changes**. But most AI quality issues come from **data changes**:

```
Monday:    Deploy. CI evals pass.                    ✅
Tuesday:   Content team updates 200 FAQ articles.    (no deploy)
Wednesday: Nightly RAG reindex runs.                 (no deploy)
Thursday:  User: "Your bot gave me wrong pricing."   ❌
Friday:    Team discovers the FAQ edit broke pricing answers 3 days ago.
```

**CI never ran. Nobody deployed. But quality broke.**

### Real scenarios CI evals will never catch:

| What changed | Why it broke AI quality | Was there a deploy? |
|---|---|---|
| Content team edited the refund policy doc | RAG now retrieves outdated chunks about refunds | **No** |
| Nightly reindex job embedded 500 new docs with bad formatting | Retrieval quality dropped — garbled chunks ranked higher | **No** |
| Product team updated pricing in the database | AI still serves old pricing from stale embeddings | **No** |
| Embedding model got deprecated, pipeline silently falls back | New embeddings are incompatible with old ones in the index | **No** |
| Vector DB rebalanced after growing 10x | Similarity scores shifted, different chunks returned for same queries | **No** |
| Third-party data feed changed format | AI's grounding data is now garbage | **No** |
| Support team deleted a "redundant" article | That article was the only source for a common question | **No** |
| Peak traffic — self-hosted model batches aggressively | Response quality drops under load, recovers at night | **No** |

**None of these trigger CI. All of them degrade quality. Users notice. Your team doesn't — until it's too late.**

### The gap

```
CODE changes  ──triggers──→  CI evals  ──→  catches code bugs        ✅
DATA changes  ──triggers──→  nothing   ──→  silent degradation       ❌
TIME passes   ──triggers──→  vigil     ──→  catches data-driven bugs ✅
```

**Vigil runs on a schedule, not on deploys.** It tests your live production endpoint — with the real data, real index, real load — and alerts when quality drops.

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

### Example 1: Content Team Edits Break RAG

**Company:** E-commerce with AI customer support chatbot.

```
Before:  Knowledge base article says "Returns within 30 days for full refund."
         Vigil baseline: refund_policy = 1.00 ✅

Content team edits:  Replaces article with "See our returns page for details."
         (No code deployed. No CI triggered.)

Next vigil run:  refund_policy = 0.20 ❌
         Alert: "refund_policy dropped 80% from baseline"

Action:  Team reverts the article. Quality restored in minutes.
Without vigil:  Users get vague refund answers for days until someone complains.
```

### Example 2: Nightly Reindex Corrupts Chunks

**Company:** SaaS with internal docs RAG for engineers.

```
Before:  RAG index has 10K clean document chunks.
         Vigil baseline: all 8 tests pass, avg 0.95 ✅

Nightly reindex:  New ETL pipeline introduces HTML tags in chunks.
         Chunks now contain "<div class='content'>The API supports..." 
         Retrieval quality drops — garbled chunks rank higher.
         (No code deployed. No CI triggered.)

Next vigil run:  avg score 0.45 ❌
         Alert on 6/8 tests degraded

Action:  Team finds the ETL bug, fixes it, re-indexes.
Without vigil:  Engineers get bad answers for a week. File tickets. Blame the AI.
```

### Example 3: Stale Embeddings After Pricing Change

**Company:** B2B SaaS. AI answers pricing questions.

```
Before:  Pro plan is $49/month. Embedded in vector DB.
         Vigil test: "How much is Pro?" → expects "49" → score 1.00 ✅

Product team changes pricing:  Pro is now $59/month. Updated on website.
         But nobody re-embedded the pricing docs.
         RAG still retrieves the old "$49" chunk.
         (No code deployed. No CI triggered.)

Next vigil run:  pricing test still passes (old embedding says $49) ✅
         BUT: You update your vigil.yaml to expect "59" after the pricing change.
         Next run: pricing = 0.00 ❌ — "49" found instead of "59"
         Alert: pricing dropped 100%

Action:  Team re-embeds pricing docs. Index updated.
Without vigil:  AI quotes wrong price to customers for weeks. Revenue impact.
```

### Example 4: Peak Load Degrades Self-Hosted Model

**Company:** Healthcare AI running local model for privacy.

```
Before:  Off-peak: model serves detailed, accurate answers.
         Vigil baseline (set at 3 AM): avg 0.92 ✅

9 AM peak traffic:  Model batches aggressively to handle load.
         Responses get shorter, less detailed, miss key info.
         (No deploy. Load-dependent degradation.)

Vigil run at 10 AM:  avg 0.61 ❌
         Alert on 4/6 tests degraded

Action:  Team scales up GPU instances during peak hours.
Without vigil:  Doctors get incomplete answers during the busiest hours. Patient safety risk.
```

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

## vigil vs Eval Frameworks

| | CI Evals (Promptfoo, DeepEval) | vigil |
|---|---|---|
| **Triggered by** | Code deploys | **Time (schedule)** |
| **Catches** | Code bugs | **Data bugs** |
| **Tests against** | Staging / test fixtures | **Live production** |
| **Tracks trends** | No (point-in-time) | **Yes (baseline + drift)** |
| **Cost** | Free | ~$0.90/month |
| **Setup** | Eval framework + CI config | **YAML + one command** |
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
