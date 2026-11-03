"""Tests for vigil core — config, runner, tracker, scorer quick checks."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from vigil_ai.config import HealthcheckConfig, TestCase, load_config
from vigil_ai.runner import TestResult
from vigil_ai.scorer import ScoreResult, _quick_checks
from vigil_ai.tracker import Tracker


# ── Config ──────────────────────────────────────────────────────

class TestConfig:
    def test_load_yaml(self, tmp_path):
        yaml_content = """
endpoint: "http://localhost:8000/api"
alert_threshold: 0.2
tests:
  - name: "test1"
    query: "Hello"
    expect:
      contains: ["world"]
  - name: "test2"
    query: "Bye"
"""
        p = tmp_path / "hc.yaml"
        p.write_text(yaml_content)

        config = load_config(p)
        assert config.endpoint == "http://localhost:8000/api"
        assert config.alert_threshold == 0.2
        assert len(config.tests) == 2
        assert config.tests[0].name == "test1"
        assert config.tests[0].expect["contains"] == ["world"]

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")

    def test_build_request_body_default(self):
        tc = TestCase(name="t", query="Hello world")
        body = tc.build_request_body()
        assert body == {"message": "Hello world"}

    def test_build_request_body_template(self):
        tc = TestCase(name="t", query="Hello", body_template='{"prompt": "{{query}}"}')
        body = tc.build_request_body()
        assert body == {"prompt": "Hello"}


# ── Quick Checks (no LLM needed) ───────────────────────────────

class TestQuickChecks:
    def _make_result(self, response: str, expect: dict) -> TestResult:
        tc = TestCase(name="test", query="q", expect=expect)
        return TestResult(test=tc, response_text=response, status_code=200, latency_ms=100)

    def test_contains_pass(self):
        result = self._make_result("30 days full refund", {"contains": ["30 days", "refund"]})
        assert _quick_checks(result) is None  # None = passed

    def test_contains_fail(self):
        result = self._make_result("We have a return policy", {"contains": ["30 days", "refund"]})
        score_result = _quick_checks(result)
        assert score_result is not None
        assert score_result.score < 0.7

    def test_min_length_pass(self):
        result = self._make_result("A" * 100, {"min_length": 50})
        assert _quick_checks(result) is None

    def test_min_length_fail(self):
        result = self._make_result("Short", {"min_length": 50})
        score_result = _quick_checks(result)
        assert score_result is not None
        assert score_result.score < 0.5

    def test_no_expectations(self):
        result = self._make_result("Anything", {})
        assert _quick_checks(result) is None  # no checks to fail


# ── Tracker ─────────────────────────────────────────────────────

class TestTracker:
    def _make_scores(self, values: dict[str, float]) -> list[ScoreResult]:
        return [
            ScoreResult(test_name=name, score=score, reasoning="test", latency_ms=100)
            for name, score in values.items()
        ]

    def test_record_and_retrieve(self, tmp_path):
        db = tmp_path / "test.db"
        tracker = Tracker(db)

        scores = self._make_scores({"test1": 0.9, "test2": 0.8})
        run_id = tracker.record_run(scores, "test_config")
        assert run_id == 1

        latest = tracker.get_latest_run()
        assert latest is not None
        assert len(latest) == 2
        tracker.close()

    def test_baseline_set_and_get(self, tmp_path):
        db = tmp_path / "test.db"
        tracker = Tracker(db)

        scores = self._make_scores({"test1": 0.9, "test2": 0.85})
        tracker.set_baseline(scores)

        assert tracker.get_baseline("test1") == 0.9
        assert tracker.get_baseline("test2") == 0.85
        assert tracker.get_baseline("nonexistent") is None
        tracker.close()

    def test_drift_detection_alert(self, tmp_path):
        db = tmp_path / "test.db"
        tracker = Tracker(db)

        # Set high baseline
        baseline = self._make_scores({"test1": 0.95, "test2": 0.90})
        tracker.set_baseline(baseline)

        # Current scores: test1 dropped significantly
        current = self._make_scores({"test1": 0.60, "test2": 0.88})
        alerts = tracker.detect_drift(current, threshold=0.15)

        assert len(alerts) == 1
        assert alerts[0].test_name == "test1"
        assert alerts[0].drop_percent > 15
        tracker.close()

    def test_drift_detection_no_alert(self, tmp_path):
        db = tmp_path / "test.db"
        tracker = Tracker(db)

        baseline = self._make_scores({"test1": 0.90})
        tracker.set_baseline(baseline)

        # Small drop — within threshold
        current = self._make_scores({"test1": 0.85})
        alerts = tracker.detect_drift(current, threshold=0.15)
        assert len(alerts) == 0
        tracker.close()

    def test_history(self, tmp_path):
        db = tmp_path / "test.db"
        tracker = Tracker(db)

        # Record 3 runs
        for score in [0.9, 0.85, 0.80]:
            scores = self._make_scores({"test1": score})
            tracker.record_run(scores)

        history = tracker.get_history("test1", limit=10)
        assert len(history) == 3
        # Most recent first
        assert history[0]["score"] == 0.80
        tracker.close()

    def test_summary(self, tmp_path):
        db = tmp_path / "test.db"
        tracker = Tracker(db)

        scores = self._make_scores({"test1": 0.9, "test2": 0.8})
        tracker.record_run(scores)

        summary = tracker.get_summary()
        assert summary["total_runs"] == 1
        assert summary["total_scores"] == 2
        assert summary["avg_score"] == 0.85
        tracker.close()


# ── Alerter Report ──────────────────────────────────────────────

class TestReport:
    def test_format_report(self):
        from vigil_ai.alerter import format_run_report
        from vigil_ai.tracker import DriftAlert

        scores = [
            ScoreResult(test_name="test1", score=0.9, reasoning="good", latency_ms=100),
            ScoreResult(test_name="test2", score=0.5, reasoning="bad", latency_ms=200),
        ]
        baselines = {"test1": 0.92, "test2": 0.88}
        alerts = [DriftAlert(
            test_name="test2", current_score=0.5, baseline_score=0.88,
            drop_percent=43.2, message="test2 dropped 43.2%"
        )]

        report = format_run_report(scores, baselines, alerts, "My App")
        assert "test1" in report
        assert "test2" in report
        assert "My App" in report
