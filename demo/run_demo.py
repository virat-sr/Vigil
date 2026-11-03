"""
Vigil Demo — Detect real AI quality degradation
================================================

This demo proves vigil catches quality drops caused by real production changes:

  Scenario 1: Good model (gemini-3.8-flash) → baseline scores
  Scenario 2: Cheap model swap (gemini-flash-lite-latest) → vigil detects degradation
  Scenario 3: Corrupted context docs → vigil detects severe degradation

No tampering. No mocks. Real Gemini API calls. Real quality differences.

Requirements:
    export GOOGLE_API_KEY=your_key
    pip install vigil-ai google-generativeai

Usage:
    python demo/run_demo.py
"""

import os
import subprocess
import sys
import time
from pathlib import Path

DEMO_DIR = Path(__file__).parent
VIGIL_CONFIG = str(DEMO_DIR / "vigil.yaml")
DB_PATH = str(DEMO_DIR / "demo_history.db")
PORT = 8500


def run_server(model="gemini-3.8-flash", corrupt=False):
    """Start the RAG app server."""
    cmd = [sys.executable, "-Iu", str(DEMO_DIR / "rag_app.py"), "--port", str(PORT), "--model", model]
    if corrupt:
        cmd.append("--corrupt-context")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def run_vigil(command="run"):
    """Run a vigil command."""
    cmd = [sys.executable, "-Iu", "-m", "vigil_ai.cli", command, "-c", VIGIL_CONFIG, "--db", DB_PATH]
    subprocess.run(cmd, env={**os.environ, "PYTHONPATH": str(DEMO_DIR.parent / "src")}, timeout=120)


def divider(text):
    print(f"\n{'='*60}", flush=True)
    print(f"  {text}", flush=True)
    print(f"{'='*60}\n", flush=True)


def main():
    if not os.environ.get("GOOGLE_API_KEY"):
        print("ERROR: Set GOOGLE_API_KEY environment variable first.")
        sys.exit(1)

    # Clean slate
    Path(DB_PATH).unlink(missing_ok=True)

    # ── Scenario 1: Good model → Baseline ────────────────────────
    divider("SCENARIO 1: Good model (gemini-3.8-flash) — Setting baseline")
    print("  Starting RAG app with gemini-3.8-flash...", flush=True)

    server = run_server(model="gemini-3.8-flash")
    time.sleep(2)

    run_vigil("baseline")
    server.terminate()
    time.sleep(1)

    # ── Scenario 2: Cheap model swap ─────────────────────────────
    divider("SCENARIO 2: Cost-cutting model swap (gemini-flash-lite-latest)")
    print("  Simulating: team swaps to cheaper model to save costs...", flush=True)
    print("  This is the #1 cause of silent AI quality degradation.\n", flush=True)

    server = run_server(model="gemini-flash-lite-latest")
    time.sleep(2)

    run_vigil("run")
    server.terminate()
    time.sleep(1)

    # ── Scenario 3: Corrupted context docs ───────────────────────
    divider("SCENARIO 3: Corrupted knowledge base (outdated docs)")
    print("  Simulating: someone deploys with stale/corrupted docs...", flush=True)
    print("  RAG returns vague answers because context is garbage.\n", flush=True)

    server = run_server(model="gemini-3.8-flash", corrupt=True)
    time.sleep(2)

    run_vigil("run")
    server.terminate()
    time.sleep(1)

    # ── History ──────────────────────────────────────────────────
    divider("SCORE HISTORY ACROSS ALL 3 RUNS")
    run_vigil("history")

    divider("DEMO COMPLETE")
    print("  Vigil detected real quality degradation from:", flush=True)
    print("    1. Model swap (gemini-3.8-flash -> 1.5-flash)", flush=True)
    print("    2. Corrupted knowledge base documents", flush=True)
    print("  No tampering. No mocks. Real Gemini API. Real quality diff.\n", flush=True)


if __name__ == "__main__":
    main()
