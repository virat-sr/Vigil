"""CLI — vigil run / baseline / history / init."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .alerter import format_run_report, print_alerts, send_webhook
from .config import load_config
from .runner import run_all
from .scorer import score_all
from .tracker import Tracker

DEFAULT_CONFIG = "vigil.yaml"


def _load_dotenv():
    """Load .env file if it exists. No dependency needed."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value and key not in os.environ:  # don't override existing env vars
            os.environ[key] = value
DEFAULT_DB = "vigil_history.db"


def _execute_run(config, tracker, webhook=None):
    """Core run logic. Returns (scores, alerts). Reused by cmd_run and cmd_watch."""
    print(f"\n  Running {len(config.tests)} tests against {config.endpoint}...\n", flush=True)

    test_results = run_all(config)
    for tr in test_results:
        status = "OK" if tr.success else "ERR"
        print(f"    [{status}] {tr.test.name} ({tr.latency_ms:.0f}ms)", flush=True)

    # Detect which judge model is being used
    from .scorer import _detect_provider, PROVIDERS
    provider, _ = _detect_provider(config.scorer_model)
    if config.scorer_model:
        judge_model = config.scorer_model
    elif provider != "none":
        judge_model = PROVIDERS[provider]["default_model"]
    else:
        judge_model = "rule-based (no API key)"

    print(f"\n  Scoring with {judge_model}...\n", flush=True)
    scores = score_all(test_results, model=config.scorer_model)
    for s in scores:
        if s.score < 0.5:
            print(f"    [{s.test_name}] score={s.score:.2f}: {s.reasoning[:120]}", flush=True)

    run_id = tracker.record_run(scores, config.name, model=judge_model)
    baselines = tracker.get_all_baselines()

    if not baselines:
        print("  (First run -- setting as baseline)\n", flush=True)
        tracker.set_baseline(scores)
        baselines = tracker.get_all_baselines()

    alerts = tracker.detect_drift(scores, config.alert_threshold)

    report = format_run_report(scores, baselines, alerts, config.name)
    print(report, flush=True)
    print_alerts(alerts)

    if webhook and alerts:
        sent = send_webhook(alerts, webhook)
        if sent:
            print(f"\n  Webhook sent to {webhook[:40]}...", flush=True)

    print(f"\n  Run #{run_id} saved to {tracker.db_path}", flush=True)
    return scores, alerts


def cmd_run(args):
    """Run all tests and report results."""
    config = load_config(args.config)
    tracker = Tracker(args.db)
    _, alerts = _execute_run(config, tracker, webhook=getattr(args, "webhook", None))
    tracker.close()
    sys.exit(1 if alerts else 0)


def cmd_watch(args):
    """Run tests on a recurring interval. Keeps running until stopped."""
    import time as _time
    from datetime import datetime

    config = load_config(args.config)
    tracker = Tracker(args.db)
    interval = args.every * 60  # convert minutes to seconds
    webhook = getattr(args, "webhook", None)

    print(f"\n  vigil WATCH MODE", flush=True)
    print(f"  Endpoint:  {config.endpoint}", flush=True)
    print(f"  Tests:     {len(config.tests)}", flush=True)
    print(f"  Interval:  every {args.every} minutes", flush=True)
    print(f"  Press Ctrl+C to stop\n", flush=True)

    run_count = 0
    try:
        while True:
            run_count += 1
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{'='*55}", flush=True)
            print(f"  Watch run #{run_count} at {now}", flush=True)
            print(f"{'='*55}", flush=True)

            try:
                _execute_run(config, tracker, webhook=webhook)
            except Exception as e:
                print(f"\n  ERROR in run #{run_count}: {e}", flush=True)

            next_run = datetime.now().strftime("%H:%M")
            print(f"\n  Next run in {args.every} minutes...", flush=True)
            _time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n\n  Watch stopped after {run_count} runs.", flush=True)
        summary = tracker.get_summary()
        print(f"  Total runs: {summary['total_runs']}, Avg score: {summary['avg_score']}", flush=True)
    finally:
        tracker.close()


def cmd_baseline(args):
    """Set current scores as the baseline."""
    config = load_config(args.config)
    tracker = Tracker(args.db)

    from .scorer import _detect_provider, PROVIDERS
    provider, _ = _detect_provider(config.scorer_model)
    judge_model = config.scorer_model or (PROVIDERS[provider]["default_model"] if provider != "none" else "rule-based")

    print(f"\n  Running baseline tests against {config.endpoint}...\n", flush=True)

    test_results = run_all(config)
    scores = score_all(test_results, model=config.scorer_model)
    tracker.set_baseline(scores)
    tracker.record_run(scores, config.name, model=judge_model)

    print("  Baseline set:\n", flush=True)
    for s in scores:
        print(f"    {s.test_name:<25} {s.score:.2f}", flush=True)

    tracker.close()


def cmd_history(args):
    """Show score history for a test or all tests."""
    tracker = Tracker(args.db)

    if args.test:
        history = tracker.get_history(args.test, limit=args.limit)
        if not history:
            print(f"  No history for '{args.test}'")
        else:
            print(f"\n  History for '{args.test}' (last {len(history)} runs):\n")
            for h in history:
                print(f"    {h['timestamp'][:19]}  score={h['score']:.2f}  latency={h['latency_ms']:.0f}ms")
    else:
        summary = tracker.get_summary()
        print(f"\n  Summary:")
        print(f"    Total runs: {summary['total_runs']}")
        print(f"    Total scores: {summary['total_scores']}")
        print(f"    Avg score: {summary['avg_score']}")

        latest = tracker.get_latest_run()
        if latest:
            print(f"\n  Latest run ({latest[0]['timestamp'][:19]}):")
            for s in latest:
                icon = "OK" if s["score"] >= 0.7 else "!!"
                print(f"    {icon:>4}  {s['test_name']:<25} {s['score']:.2f}")

    tracker.close()


def cmd_init(args):
    """Create a sample vigil.yaml."""
    path = Path(args.config)
    if path.exists() and not args.force:
        print(f"  {path} already exists. Use --force to overwrite.")
        sys.exit(1)

    sample = '''# vigil configuration
name: "My AI App"
endpoint: "http://localhost:8000/api/chat"
response_field: "response"  # field in API JSON response containing the answer
alert_threshold: 0.15       # alert if quality drops >15% from baseline
# scorer_model: "gpt-4o-mini"       # OpenAI (set OPENAI_API_KEY)
# scorer_model: "gemini-3.8-flash"  # Gemini (set GOOGLE_API_KEY)
scorer_model: ""                     # empty = auto-detect from available API key
timeout: 30

tests:
  - name: "basic_query"
    query: "What is your return policy?"
    expect:
      contains: ["30 days", "refund"]
      tone: "professional"

  - name: "factual_query"
    query: "What are your business hours?"
    expect:
      contains_numbers: true
      no_hallucination: true

  - name: "complex_query"
    query: "Compare the Pro and Enterprise plans"
    expect:
      min_length: 100
      grounded_in_context: true

  - name: "edge_case_empty"
    query: ""
    expect:
      tone: "helpful"

  # Add your own tests below:
  # - name: "my_test"
  #   query: "Your test query here"
  #   expect:
  #     contains: ["expected", "keywords"]
'''
    path.write_text(sample, encoding="utf-8")
    print(f"  Created {path}")
    print(f"  Edit it, then run: vigil run")


def main():
    _load_dotenv()

    parser = argparse.ArgumentParser(
        prog="vigil",
        description="Uptime monitoring for AI quality. Proactive testing, drift detection, alerting.",
    )
    sub = parser.add_subparsers(dest="command")

    # Common args added to each subparser
    def add_common(p):
        p.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="Path to vigil YAML config")
        p.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite history database")

    # run
    p_run = sub.add_parser("run", help="Run all tests and report results")
    add_common(p_run)
    p_run.add_argument("--webhook", help="Webhook URL for alerts (Slack/Discord)")

    # watch
    p_watch = sub.add_parser("watch", help="Run tests on a recurring interval (continuous monitoring)")
    add_common(p_watch)
    p_watch.add_argument("--every", type=int, default=60, help="Run every N minutes (default: 60)")
    p_watch.add_argument("--webhook", help="Webhook URL for alerts (Slack/Discord)")

    # baseline
    p_base = sub.add_parser("baseline", help="Run tests and set results as the baseline")
    add_common(p_base)

    # history
    p_hist = sub.add_parser("history", help="Show score history")
    add_common(p_hist)
    p_hist.add_argument("--test", help="Show history for a specific test")
    p_hist.add_argument("--limit", type=int, default=20, help="Number of records")

    # init
    p_init = sub.add_parser("init", help="Create a sample vigil.yaml")
    p_init.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="Output path for YAML")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing file")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Open the visual quality dashboard in your browser")
    p_dash.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite history database")
    p_dash.add_argument("--port", type=int, default=9090, help="Dashboard port (default: 9090)")

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "watch":
        cmd_watch(args)
    elif args.command == "baseline":
        cmd_baseline(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "init":
        cmd_init(args)
    elif args.command == "dashboard":
        from .dashboard import serve_dashboard
        serve_dashboard(db_path=args.db, port=args.port)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
