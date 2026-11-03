"""Vigil Dashboard — visual quality monitoring UI.

Run: vigil dashboard
     vigil dashboard --db demo/demo_history.db --port 9090
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs


def _query_db(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result


def _get_dashboard_data(db_path: str) -> dict:
    """Pull all data needed for the dashboard."""
    runs = _query_db(db_path, "SELECT id, timestamp, config_name FROM runs ORDER BY id")
    scores = _query_db(db_path, """
        SELECT s.run_id, s.test_name, s.score, s.reasoning, s.latency_ms, s.error, r.timestamp
        FROM scores s JOIN runs r ON s.run_id = r.id
        ORDER BY r.id, s.test_name
    """)
    baselines = _query_db(db_path, "SELECT test_name, score, set_at FROM baselines")

    # Group scores by test name for time series
    test_names = sorted(set(s["test_name"] for s in scores))
    series = {}
    for name in test_names:
        series[name] = [
            {"run_id": s["run_id"], "timestamp": s["timestamp"], "score": s["score"],
             "reasoning": s["reasoning"], "latency_ms": s["latency_ms"]}
            for s in scores if s["test_name"] == name
        ]

    # Per-run summaries
    run_summaries = []
    for run in runs:
        run_scores = [s for s in scores if s["run_id"] == run["id"]]
        avg = sum(s["score"] for s in run_scores) / len(run_scores) if run_scores else 0
        passed = sum(1 for s in run_scores if s["score"] >= 0.7)
        failed = sum(1 for s in run_scores if s["score"] < 0.4)
        run_summaries.append({
            "id": run["id"], "timestamp": run["timestamp"],
            "avg_score": round(avg, 3), "passed": passed, "failed": failed,
            "total": len(run_scores),
        })

    baseline_map = {b["test_name"]: b["score"] for b in baselines}

    # Per-run details (all runs, not just latest) — for clickable dashboard
    run_details = {}
    for run in runs:
        details = []
        for s in scores:
            if s["run_id"] == run["id"]:
                bl = baseline_map.get(s["test_name"])
                drift_pct = round(((s["score"] - bl) / bl) * 100, 1) if bl and bl > 0 else None
                details.append({**s, "baseline": bl, "drift_pct": drift_pct})
        run_details[run["id"]] = details

    latest = run_details.get(runs[-1]["id"], []) if runs else []

    return {
        "test_names": test_names,
        "series": series,
        "runs": run_summaries,
        "baselines": baseline_map,
        "latest": latest,
        "run_details": run_details,
        "total_runs": len(runs),
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Vigil Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, system-ui, sans-serif; background: #0a0e1a; color: #e2e8f0; }

  .header { background: linear-gradient(135deg, #1a1f35 0%, #0d1117 100%); padding: 24px 32px; border-bottom: 1px solid #1e293b; display: flex; align-items: center; justify-content: space-between; }
  .header h1 { font-size: 22px; font-weight: 700; }
  .header h1 span { color: #60a5fa; }
  .header .meta { color: #94a3b8; font-size: 13px; }

  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }

  /* Health Banner */
  .health-banner { border-radius: 12px; padding: 24px 32px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; }
  .health-good { background: linear-gradient(135deg, #065f46 0%, #064e3b 100%); border: 1px solid #10b981; }
  .health-warn { background: linear-gradient(135deg, #78350f 0%, #713f12 100%); border: 1px solid #f59e0b; }
  .health-bad { background: linear-gradient(135deg, #7f1d1d 0%, #991b1b 100%); border: 1px solid #ef4444; }
  .health-score { font-size: 48px; font-weight: 800; }
  .health-label { font-size: 14px; color: #94a3b8; margin-top: 4px; }
  .health-stats { display: flex; gap: 32px; }
  .health-stat { text-align: center; }
  .health-stat .num { font-size: 28px; font-weight: 700; }
  .health-stat .label { font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }

  /* Cards */
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }
  .card { background: #111827; border: 1px solid #1e293b; border-radius: 12px; padding: 20px; }
  .card-full { grid-column: 1 / -1; }
  .card h2 { font-size: 15px; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 16px; }

  /* Chart */
  .chart-container { position: relative; height: 300px; }

  /* Test Results Table */
  .results-table { width: 100%; border-collapse: collapse; }
  .results-table th { text-align: left; padding: 10px 12px; font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; border-bottom: 1px solid #1e293b; }
  .results-table td { padding: 12px; border-bottom: 1px solid #1e293b; font-size: 14px; }
  .results-table tr:hover { background: #1e293b; }

  .badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .badge-pass { background: #065f46; color: #34d399; }
  .badge-warn { background: #78350f; color: #fbbf24; }
  .badge-fail { background: #7f1d1d; color: #f87171; }

  .score-bar { display: inline-block; height: 8px; border-radius: 4px; min-width: 4px; }
  .score-bar-bg { display: inline-block; width: 100px; height: 8px; background: #1e293b; border-radius: 4px; position: relative; }

  .drift-pos { color: #34d399; }
  .drift-neg { color: #f87171; }
  .drift-neutral { color: #64748b; }

  /* Run History */
  .run-pills { display: flex; gap: 8px; flex-wrap: wrap; }
  .run-pill { padding: 6px 14px; border-radius: 8px; font-size: 13px; border: 1px solid #1e293b; background: #1e293b; }
  .run-pill { cursor: pointer; transition: transform 0.1s, box-shadow 0.2s; }
  .run-pill:hover { transform: scale(1.05); }
  .run-pill.good { border-color: #10b981; color: #34d399; }
  .run-pill.warn { border-color: #f59e0b; color: #fbbf24; }
  .run-pill.bad { border-color: #ef4444; color: #f87171; }
  .run-pill.selected { box-shadow: 0 0 0 2px #60a5fa; transform: scale(1.08); }

  .reasoning { font-size: 12px; color: #64748b; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .reasoning:hover { white-space: normal; }

  .table-header-run { font-size: 13px; color: #60a5fa; margin-bottom: 12px; }

  .footer { text-align: center; padding: 24px; color: #475569; font-size: 12px; }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1><span>vigil</span> dashboard</h1>
    <div class="meta">AI Quality Monitoring</div>
  </div>
  <div class="meta">Last updated: <span id="last-update"></span></div>
</div>

<div class="container">
  <div class="health-banner" id="health-banner">
    <div>
      <div class="health-score" id="health-score">—</div>
      <div class="health-label">Overall Quality Score</div>
    </div>
    <div class="health-stats">
      <div class="health-stat"><div class="num" id="stat-passed">—</div><div class="label">Passed</div></div>
      <div class="health-stat"><div class="num" id="stat-degraded">—</div><div class="label">Degraded</div></div>
      <div class="health-stat"><div class="num" id="stat-failed">—</div><div class="label">Failed</div></div>
      <div class="health-stat"><div class="num" id="stat-runs">—</div><div class="label">Total Runs</div></div>
    </div>
  </div>

  <div class="grid">
    <div class="card card-full">
      <h2>Quality Score Over Time</h2>
      <div class="chart-container"><canvas id="timeChart"></canvas></div>
    </div>

    <div class="card card-full">
      <h2>Test Results — <span id="selected-run-label" class="table-header-run">Latest Run</span></h2>
      <table class="results-table">
        <thead><tr><th>Test</th><th>Score</th><th></th><th>Baseline</th><th>Drift</th><th>Status</th><th>Reasoning</th></tr></thead>
        <tbody id="results-body"></tbody>
      </table>
    </div>

    <div class="card">
      <h2>Score Distribution (Latest)</h2>
      <div class="chart-container"><canvas id="distChart"></canvas></div>
    </div>

    <div class="card">
      <h2>Run History</h2>
      <div class="run-pills" id="run-pills"></div>
    </div>
  </div>
</div>

<div class="footer">vigil — uptime monitoring for AI quality</div>

<script>
const DATA = __DATA_PLACEHOLDER__;
const RUN_DETAILS = DATA.run_details || {};

// ── Health banner (latest run) ─────────────────────────────────
const latest = DATA.latest || [];
const avgScore = latest.length ? (latest.reduce((s,t) => s + t.score, 0) / latest.length) : 0;
const passed = latest.filter(t => t.score >= 0.7).length;
const failed = latest.filter(t => t.score < 0.4).length;
const degraded = latest.filter(t => t.drift_pct !== null && t.drift_pct < -15).length;

document.getElementById('health-score').textContent = avgScore.toFixed(2);
document.getElementById('stat-passed').textContent = passed;
document.getElementById('stat-degraded').textContent = degraded;
document.getElementById('stat-failed').textContent = failed;
document.getElementById('stat-runs').textContent = DATA.total_runs;

const banner = document.getElementById('health-banner');
if (avgScore >= 0.8 && degraded === 0) banner.className = 'health-banner health-good';
else if (avgScore >= 0.5) banner.className = 'health-banner health-warn';
else banner.className = 'health-banner health-bad';

if (DATA.runs.length) {
  document.getElementById('last-update').textContent = DATA.runs[DATA.runs.length-1].timestamp.slice(0,19);
}

// ── Render test results table for any run ──────────────────────
function renderTable(tests, runLabel) {
  const tbody = document.getElementById('results-body');
  tbody.innerHTML = '';
  document.getElementById('selected-run-label').textContent = runLabel;

  tests.forEach(t => {
    const badge = t.score >= 0.7 ? 'badge-pass' : t.score >= 0.4 ? 'badge-warn' : 'badge-fail';
    const status = t.score >= 0.7 ? 'PASS' : t.score >= 0.4 ? 'WARN' : 'FAIL';
    const driftClass = t.drift_pct > 0 ? 'drift-pos' : t.drift_pct < -15 ? 'drift-neg' : 'drift-neutral';
    const driftText = t.drift_pct !== null ? (t.drift_pct > 0 ? '+' : '') + t.drift_pct + '%' : '  ';
    const barW = Math.max(t.score * 100, 2);
    const barColor = t.score >= 0.7 ? '#10b981' : t.score >= 0.4 ? '#f59e0b' : '#ef4444';

    tbody.innerHTML += '<tr>' +
      '<td><strong>' + t.test_name + '</strong></td>' +
      '<td>' + t.score.toFixed(2) + '</td>' +
      '<td><span class="score-bar-bg"><span class="score-bar" style="width:' + barW + '%;background:' + barColor + '"></span></span></td>' +
      '<td>' + (t.baseline !== null && t.baseline !== undefined ? t.baseline.toFixed(2) : '  ') + '</td>' +
      '<td class="' + driftClass + '">' + driftText + '</td>' +
      '<td><span class="badge ' + badge + '">' + status + '</span></td>' +
      '<td class="reasoning">' + (t.reasoning||'') + '</td>' +
      '</tr>';
  });

  // Update distribution chart
  updateDistChart(tests);
}

// ── Select a run (called by chart click and pill click) ────────
let selectedRunId = null;

function selectRun(runId) {
  const run = DATA.runs.find(r => r.id === runId);
  const details = RUN_DETAILS[runId] || [];
  if (!details.length) return;

  selectedRunId = runId;
  const label = 'Run #' + runId + ' (' + (run ? run.timestamp.slice(0,16) : '') + ') — avg ' + (run ? run.avg_score.toFixed(2) : '');
  renderTable(details, label);

  // Highlight selected pill
  document.querySelectorAll('.run-pill').forEach(p => p.classList.remove('selected'));
  const pill = document.getElementById('pill-' + runId);
  if (pill) pill.classList.add('selected');
}

// ── Time series chart ──────────────────────────────────────────
const colors = ['#60a5fa','#f472b6','#34d399','#fbbf24','#a78bfa','#fb923c','#22d3ee','#e879f9','#4ade80','#f87171'];
const datasets = DATA.test_names.map((name, i) => ({
  label: name,
  data: (DATA.series[name]||[]).map(p => ({x: 'Run #' + p.run_id, y: p.score})),
  borderColor: colors[i % colors.length],
  backgroundColor: colors[i % colors.length] + '20',
  tension: 0.3, fill: false, pointRadius: 5, pointHoverRadius: 8, borderWidth: 2,
}));

// Baseline dashed line
if (Object.keys(DATA.baselines).length) {
  const blAvg = Object.values(DATA.baselines).reduce((a,b) => a+b, 0) / Object.values(DATA.baselines).length;
  const labels = datasets[0] ? datasets[0].data.map(d => d.x) : [];
  datasets.push({
    label: 'Baseline',
    data: labels.map(x => ({x, y: blAvg})),
    borderColor: '#475569', borderDash: [6,4], borderWidth: 2, pointRadius: 0, fill: false,
  });
}

const timeChart = new Chart(document.getElementById('timeChart'), {
  type: 'line',
  data: { datasets },
  options: {
    responsive: true, maintainAspectRatio: false,
    scales: {
      x: { type: 'category', grid: {color:'#1e293b'}, ticks: {color:'#64748b'} },
      y: { min: 0, max: 1.05, grid: {color:'#1e293b'}, ticks: {color:'#64748b'} },
    },
    plugins: {
      legend: { labels: {color:'#94a3b8', usePointStyle: true, pointStyle: 'circle'} },
      tooltip: { callbacks: { title: (items) => items[0] ? items[0].raw.x : '' } },
    },
    onClick: (evt, elements) => {
      if (elements.length > 0) {
        const idx = elements[0].index;
        const runId = DATA.runs[idx] ? DATA.runs[idx].id : null;
        if (runId) selectRun(runId);
      }
    },
  },
});

// ── Distribution chart (updates when run is selected) ──────────
let distChart = new Chart(document.getElementById('distChart'), {
  type: 'bar',
  data: {
    labels: latest.map(t => t.test_name),
    datasets: [{
      data: latest.map(t => t.score),
      backgroundColor: latest.map(t => t.score >= 0.7 ? '#10b98180' : t.score >= 0.4 ? '#f59e0b80' : '#ef444480'),
      borderColor: latest.map(t => t.score >= 0.7 ? '#10b981' : t.score >= 0.4 ? '#f59e0b' : '#ef4444'),
      borderWidth: 1, borderRadius: 4,
    }]
  },
  options: {
    responsive: true, maintainAspectRatio: false, indexAxis: 'y',
    scales: { x: {min:0,max:1,grid:{color:'#1e293b'},ticks:{color:'#64748b'}}, y: {grid:{display:false},ticks:{color:'#94a3b8',font:{size:11}}} },
    plugins: { legend: {display: false} },
  },
});

function updateDistChart(tests) {
  distChart.data.labels = tests.map(t => t.test_name);
  distChart.data.datasets[0].data = tests.map(t => t.score);
  distChart.data.datasets[0].backgroundColor = tests.map(t => t.score >= 0.7 ? '#10b98180' : t.score >= 0.4 ? '#f59e0b80' : '#ef444480');
  distChart.data.datasets[0].borderColor = tests.map(t => t.score >= 0.7 ? '#10b981' : t.score >= 0.4 ? '#f59e0b' : '#ef4444');
  distChart.update();
}

// ── Run history pills (clickable) ──────────────────────────────
const pills = document.getElementById('run-pills');
DATA.runs.forEach(r => {
  const cls = r.avg_score >= 0.8 ? 'good' : r.avg_score >= 0.5 ? 'warn' : 'bad';
  pills.innerHTML += '<div class="run-pill ' + cls + '" id="pill-' + r.id + '" onclick="selectRun(' + r.id + ')">' +
    'Run #' + r.id + ' — ' + r.avg_score.toFixed(2) + ' (' + r.timestamp.slice(5,16) + ')</div>';
});

// ── Initial render (latest run) ────────────────────────────────
renderTable(latest, 'Latest Run (#' + (DATA.runs.length ? DATA.runs[DATA.runs.length-1].id : '') + ')');
if (DATA.runs.length) {
  const lastPill = document.getElementById('pill-' + DATA.runs[DATA.runs.length-1].id);
  if (lastPill) lastPill.classList.add('selected');
}
</script>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    db_path = "vigil_history.db"

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/data":
            data = _get_dashboard_data(self.db_path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())
            return

        # Serve dashboard HTML with embedded data
        data = _get_dashboard_data(self.db_path)
        html = DASHBOARD_HTML.replace("__DATA_PLACEHOLDER__", json.dumps(data))
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass  # silent


def serve_dashboard(db_path: str = "vigil_history.db", port: int = 9090):
    """Start the dashboard web server."""
    DashboardHandler.db_path = db_path
    server = ThreadingHTTPServer(("localhost", port), DashboardHandler)
    print(f"\n  vigil dashboard", flush=True)
    print(f"  Database: {db_path}", flush=True)
    print(f"  Open:     http://localhost:{port}", flush=True)
    print(f"  API:      http://localhost:{port}/api/data", flush=True)
    print(f"  Press Ctrl+C to stop\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()
