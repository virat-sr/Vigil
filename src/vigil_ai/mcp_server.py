"""Vigil MCP Server — expose vigil tools to Claude Code, Claude Desktop, Cursor, etc.

Run:
    python -m vigil_ai.mcp_server                  # stdio mode (for Claude Code)
    python -m vigil_ai.mcp_server --transport sse   # SSE mode (for web clients)

Configure in Claude Code:
    Add to .claude/settings.json or run:
    claude mcp add vigil -- python -m vigil_ai.mcp_server
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

server = MCPServer(
    name="vigil",
    instructions=(
        "Vigil monitors AI quality. Use these tools to check if an AI endpoint is healthy, "
        "view quality history, and detect degradation. "
        "Before running, ensure a vigil.yaml config exists (use vigil_init to create one)."
    ),
)


def _find_config(config_path: str = "vigil.yaml") -> str:
    """Find vigil.yaml — check CWD and common locations."""
    candidates = [
        config_path,
        os.path.join(os.getcwd(), config_path),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return config_path  # let it fail with a clear error


@server.tool()
def vigil_run(config_path: str = "vigil.yaml", db_path: str = "vigil_history.db") -> str:
    """Run all quality tests against your AI endpoint. Scores responses, detects drift, returns report.

    Args:
        config_path: Path to vigil.yaml config file (default: vigil.yaml in current directory)
        db_path: Path to SQLite history database (default: vigil_history.db)
    """
    from .alerter import format_run_report, print_alerts
    from .config import load_config
    from .runner import run_all
    from .scorer import score_all
    from .tracker import Tracker

    try:
        config = load_config(_find_config(config_path))
        tracker = Tracker(db_path)

        test_results = run_all(config)
        scores = score_all(test_results, model=config.scorer_model)

        run_id = tracker.record_run(scores, config.name)
        baselines = tracker.get_all_baselines()

        if not baselines:
            tracker.set_baseline(scores)
            baselines = tracker.get_all_baselines()

        alerts = tracker.detect_drift(scores, config.alert_threshold)
        report = format_run_report(scores, baselines, alerts, config.name)

        alert_text = ""
        if alerts:
            alert_text = "\n\nQUALITY ALERTS:\n" + "\n".join(f"  !! {a.message}" for a in alerts)

        tracker.close()
        return f"{report}{alert_text}\n\nRun #{run_id} saved."

    except Exception as e:
        return f"Error: {e}"


@server.tool()
def vigil_history(test_name: str = "", db_path: str = "vigil_history.db", limit: int = 10) -> str:
    """Show quality score history. Optionally filter by test name.

    Args:
        test_name: Specific test to show history for (empty = summary of all)
        db_path: Path to SQLite history database
        limit: Number of recent records to show
    """
    from .tracker import Tracker

    try:
        tracker = Tracker(db_path)

        if test_name:
            history = tracker.get_history(test_name, limit=limit)
            if not history:
                tracker.close()
                return f"No history for '{test_name}'"

            lines = [f"History for '{test_name}' (last {len(history)} runs):"]
            for h in history:
                lines.append(f"  {h['timestamp'][:19]}  score={h['score']:.2f}  latency={h['latency_ms']:.0f}ms")
            tracker.close()
            return "\n".join(lines)
        else:
            summary = tracker.get_summary()
            latest = tracker.get_latest_run()

            lines = [
                f"Total runs: {summary['total_runs']}",
                f"Total scores: {summary['total_scores']}",
                f"Avg score: {summary['avg_score']}",
            ]

            if latest:
                lines.append(f"\nLatest run ({latest[0]['timestamp'][:19]}):")
                for s in latest:
                    icon = "OK" if s["score"] >= 0.7 else "!!"
                    lines.append(f"  {icon:>4}  {s['test_name']:<25} {s['score']:.2f}")

            tracker.close()
            return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


@server.tool()
def vigil_baseline(config_path: str = "vigil.yaml", db_path: str = "vigil_history.db") -> str:
    """Run tests and set current scores as the quality baseline for drift detection.

    Args:
        config_path: Path to vigil.yaml config file
        db_path: Path to SQLite history database
    """
    from .config import load_config
    from .runner import run_all
    from .scorer import score_all
    from .tracker import Tracker

    try:
        config = load_config(_find_config(config_path))
        tracker = Tracker(db_path)

        test_results = run_all(config)
        scores = score_all(test_results, model=config.scorer_model)
        tracker.set_baseline(scores)
        tracker.record_run(scores, config.name)

        lines = ["Baseline set:"]
        for s in scores:
            lines.append(f"  {s.test_name:<25} {s.score:.2f}")

        tracker.close()
        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


@server.tool()
def vigil_init(config_path: str = "vigil.yaml") -> str:
    """Create a sample vigil.yaml configuration file in the current directory.

    Args:
        config_path: Where to create the config file (default: vigil.yaml)
    """
    path = Path(config_path)
    if path.exists():
        return f"{path} already exists. Delete it first or use a different path."

    sample = """# vigil.yaml — AI quality monitoring config
name: "My AI App"
endpoint: "http://localhost:8000/api/chat"
response_field: "response"
alert_threshold: 0.15
scorer_model: "gemini-3.8-flash"
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
"""
    path.write_text(sample, encoding="utf-8")
    return f"Created {path}. Edit the endpoint and tests, then use vigil_run."


def main():
    """Entry point for MCP server."""
    import argparse
    parser = argparse.ArgumentParser(description="Vigil MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.transport == "sse":
        server.run(transport="sse", port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
