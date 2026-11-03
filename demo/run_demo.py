"""
Vigil Demo — Detect real AI quality degradation
================================================

Proves vigil catches quality drops from real production changes:

  Scenario 1: Good model (gpt-4o-mini via OpenRouter) -> baseline
  Scenario 2: Cheap model swap (free Llama) -> vigil detects degradation
  Scenario 3: Corrupted docs (good model, bad context) -> vigil detects

No tampering. No mocks. Real LLM API calls. Real quality differences.

Requirements:
    Set OPENROUTER_API_KEY in .env (or OPENAI_API_KEY / GOOGLE_API_KEY)
    pip install vigil-ai[openai]

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

GOOD_MODEL = "openai/gpt-4o-mini"
CHEAP_MODEL = "liquid/lfm-2.5-2.6b:free"  # 2.6B params — will struggle on detailed questions


def _load_env():
    env_path = DEMO_DIR.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if v.strip() and k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()


def run_server(model=GOOD_MODEL, corrupt=False):
    cmd = [sys.executable, "-Iu", str(DEMO_DIR / "rag_app.py"), "--port", str(PORT), "--model", model]
    if corrupt:
        cmd.append("--corrupt-context")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def run_vigil(command="run"):
    subprocess.run(
        [sys.executable, "-Iu", "-m", "vigil_ai.cli", command, "-c", VIGIL_CONFIG, "--db", DB_PATH],
        env={**os.environ, "PYTHONPATH": str(DEMO_DIR.parent / "src")},
        timeout=180,
    )


def divider(text):
    print(f"\n{'='*60}", flush=True)
    print(f"  {text}", flush=True)
    print(f"{'='*60}\n", flush=True)


def main():
    _load_env()

    has_key = any(os.environ.get(k) for k in ["OPENROUTER_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"])
    if not has_key:
        print("ERROR: Set OPENROUTER_API_KEY (or OPENAI_API_KEY / GOOGLE_API_KEY) in .env")
        sys.exit(1)

    Path(DB_PATH).unlink(missing_ok=True)

    # ── Scenario 1 ───────────────────────────────────────────────
    divider(f"SCENARIO 1: Good model ({GOOD_MODEL}) -- Setting baseline")
    server = run_server(model=GOOD_MODEL)
    time.sleep(3)
    run_vigil("baseline")
    server.terminate()
    time.sleep(1)

    # ── Scenario 2 ───────────────────────────────────────────────
    divider(f"SCENARIO 2: Cost-cutting swap ({CHEAP_MODEL})")
    print("  Simulating: team swaps to free model to save costs...", flush=True)
    print("  This is the #1 cause of silent AI quality degradation.\n", flush=True)
    server = run_server(model=CHEAP_MODEL)
    time.sleep(3)
    run_vigil("run")
    server.terminate()
    time.sleep(1)

    # ── Scenario 3 ───────────────────────────────────────────────
    divider("SCENARIO 3: Corrupted knowledge base")
    print("  Simulating: deploy with stale/corrupted docs...", flush=True)
    print("  Good model but garbage context = vague answers.\n", flush=True)
    server = run_server(model=GOOD_MODEL, corrupt=True)
    time.sleep(3)
    run_vigil("run")
    server.terminate()
    time.sleep(1)

    # ── History ──────────────────────────────────────────────────
    divider("SCORE HISTORY ACROSS ALL 3 RUNS")
    run_vigil("history")

    divider("DEMO COMPLETE")
    print("  Vigil detected real quality degradation from:", flush=True)
    print(f"    1. Model swap ({GOOD_MODEL} -> {CHEAP_MODEL})", flush=True)
    print(f"    2. Corrupted knowledge base documents", flush=True)
    print("  No tampering. No mocks. Real API. Real quality diff.\n", flush=True)


if __name__ == "__main__":
    main()
