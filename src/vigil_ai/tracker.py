"""Tracker — stores scores over time in SQLite, detects drift, computes baselines."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .scorer import ScoreResult

DEFAULT_DB = "healthcheck_history.db"


@dataclass
class DriftAlert:
    """Alert when a test's quality has degraded."""

    test_name: str
    current_score: float
    baseline_score: float
    drop_percent: float
    message: str


class Tracker:
    """SQLite-backed score history and drift detection."""

    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self.db_path))
        self._init_db()

    def _init_db(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                config_name TEXT DEFAULT '',
                model TEXT DEFAULT ''
            )
        """)
        # Migration: add model column if missing (existing DBs)
        try:
            self._conn.execute("SELECT model FROM runs LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.execute("ALTER TABLE runs ADD COLUMN model TEXT DEFAULT ''")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                test_name TEXT NOT NULL,
                score REAL NOT NULL,
                reasoning TEXT DEFAULT '',
                latency_ms REAL DEFAULT 0,
                error TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS baselines (
                test_name TEXT PRIMARY KEY,
                score REAL NOT NULL,
                set_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def record_run(self, scores: list[ScoreResult], config_name: str = "", model: str = "") -> int:
        """Record a complete healthcheck run. Returns run_id."""
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO runs (timestamp, config_name, model) VALUES (?, ?, ?)",
            (now, config_name, model),
        )
        run_id = cursor.lastrowid

        for s in scores:
            self._conn.execute(
                "INSERT INTO scores (run_id, test_name, score, reasoning, latency_ms, error) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, s.test_name, s.score, s.reasoning, s.latency_ms, s.error),
            )
        self._conn.commit()
        return run_id

    def set_baseline(self, scores: list[ScoreResult]):
        """Set current scores as the baseline for drift detection."""
        now = datetime.now().isoformat()
        for s in scores:
            self._conn.execute(
                "INSERT OR REPLACE INTO baselines (test_name, score, set_at) VALUES (?, ?, ?)",
                (s.test_name, s.score, now),
            )
        self._conn.commit()

    def get_baseline(self, test_name: str) -> float | None:
        """Get baseline score for a test. Returns None if no baseline set."""
        row = self._conn.execute(
            "SELECT score FROM baselines WHERE test_name = ?", (test_name,)
        ).fetchone()
        return row[0] if row else None

    def get_all_baselines(self) -> dict[str, float]:
        """Get all baselines as {test_name: score}."""
        rows = self._conn.execute("SELECT test_name, score FROM baselines").fetchall()
        return {name: score for name, score in rows}

    def detect_drift(self, scores: list[ScoreResult], threshold: float = 0.15) -> list[DriftAlert]:
        """Compare current scores against baselines. Alert if degraded beyond threshold."""
        alerts = []
        for s in scores:
            baseline = self.get_baseline(s.test_name)
            if baseline is None or baseline == 0:
                continue

            drop = (baseline - s.score) / baseline
            if drop > threshold:
                alerts.append(DriftAlert(
                    test_name=s.test_name,
                    current_score=s.score,
                    baseline_score=baseline,
                    drop_percent=round(drop * 100, 1),
                    message=f"{s.test_name}: score dropped {round(drop * 100, 1)}% "
                            f"({baseline:.2f} -> {s.score:.2f})",
                ))
        return alerts

    def get_history(self, test_name: str, limit: int = 20) -> list[dict]:
        """Get score history for a test, most recent first."""
        rows = self._conn.execute(
            "SELECT r.timestamp, s.score, s.reasoning, s.latency_ms "
            "FROM scores s JOIN runs r ON s.run_id = r.id "
            "WHERE s.test_name = ? ORDER BY r.timestamp DESC LIMIT ?",
            (test_name, limit),
        ).fetchall()
        return [
            {"timestamp": ts, "score": score, "reasoning": reason, "latency_ms": lat}
            for ts, score, reason, lat in rows
        ]

    def get_latest_run(self) -> list[dict] | None:
        """Get the most recent run's scores."""
        row = self._conn.execute(
            "SELECT id, timestamp FROM runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        run_id, timestamp = row
        scores = self._conn.execute(
            "SELECT test_name, score, reasoning, latency_ms, error "
            "FROM scores WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        return [
            {"test_name": n, "score": s, "reasoning": r, "latency_ms": l, "error": e, "timestamp": timestamp}
            for n, s, r, l, e in scores
        ]

    def get_summary(self) -> dict:
        """Get summary stats across all runs."""
        total_runs = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        total_scores = self._conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]
        avg_score = self._conn.execute("SELECT AVG(score) FROM scores").fetchone()[0]
        return {
            "total_runs": total_runs,
            "total_scores": total_scores,
            "avg_score": round(avg_score, 3) if avg_score else 0,
        }

    def close(self):
        self._conn.close()
