"""Alerter — outputs alerts to console and optional webhook (Slack/Discord)."""

from __future__ import annotations

import json
from urllib.request import urlopen, Request

from .tracker import DriftAlert


def print_alerts(alerts: list[DriftAlert]) -> None:
    """Print alerts to console."""
    if not alerts:
        return

    print(f"\n  {'!'*3} QUALITY ALERTS {'!'*3}")
    for alert in alerts:
        icon = "!!" if alert.drop_percent > 25 else "!"
        print(f"  {icon} {alert.message}")


def send_webhook(alerts: list[DriftAlert], webhook_url: str) -> bool:
    """Send alerts to a webhook (Slack/Discord compatible).

    Returns True if sent successfully.
    """
    if not alerts or not webhook_url:
        return False

    lines = ["*Vigil Alert*"]
    for a in alerts:
        lines.append(f"- {a.test_name}: score dropped {a.drop_percent}% ({a.baseline_score:.2f} -> {a.current_score:.2f})")

    payload = {"text": "\n".join(lines)}

    try:
        req = Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def format_run_report(
    scores: list,
    baselines: dict[str, float],
    alerts: list[DriftAlert],
    config_name: str = "",
) -> str:
    """Format a complete run report as a string."""
    from datetime import datetime
    lines = []
    lines.append(f"  vigil — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if config_name:
        lines.append(f"  Config: {config_name}")
    lines.append("")

    total = len(scores)
    passed = sum(1 for s in scores if s.score >= 0.7)
    degraded = len(alerts)
    failed = sum(1 for s in scores if s.score < 0.4)

    for s in scores:
        baseline = baselines.get(s.test_name)
        if s.error:
            icon = "X"
            delta = ""
        elif s.score >= 0.7:
            icon = "OK"
            delta = ""
        else:
            icon = "!!"
            delta = ""

        if baseline is not None and baseline > 0:
            pct = ((s.score - baseline) / baseline) * 100
            delta = f"  {pct:+.0f}%"
            if pct < -15:
                icon = "!!"
                delta += " DEGRADED"

        baseline_str = f"(baseline: {baseline:.2f})" if baseline else "(no baseline)"
        lines.append(f"  {icon:>4}  {s.test_name:<25} {s.score:.2f}  {baseline_str}{delta}")

    lines.append("")
    lines.append(f"  Overall: {passed}/{total} pass, {degraded} degraded, {failed} failed")

    avg = sum(s.score for s in scores) / total if total > 0 else 0
    baseline_avg = sum(baselines.values()) / len(baselines) if baselines else 0
    if baseline_avg > 0:
        overall_pct = ((avg - baseline_avg) / baseline_avg) * 100
        lines.append(f"  Average score: {avg:.2f} (baseline: {baseline_avg:.2f}) {overall_pct:+.1f}%")
    else:
        lines.append(f"  Average score: {avg:.2f}")

    return "\n".join(lines)
