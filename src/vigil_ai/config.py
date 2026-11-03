"""Load and validate YAML test suite configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class TestCase:
    """A single test query with expectations."""

    name: str
    query: str
    expect: dict = field(default_factory=dict)
    method: str = "POST"
    headers: dict = field(default_factory=dict)
    body_template: str | None = None  # jinja-like: '{"message": "{{query}}"}'

    def build_request_body(self) -> dict:
        """Build the HTTP request body for this test."""
        if self.body_template:
            # Simple {{query}} replacement
            body_str = self.body_template.replace("{{query}}", self.query)
            import json
            return json.loads(body_str)
        # Default: common chat API format
        return {"message": self.query}


@dataclass
class HealthcheckConfig:
    """Full healthcheck configuration from YAML."""

    endpoint: str
    tests: list[TestCase]
    schedule: str = "manual"
    alert_threshold: float = 0.15  # alert if quality drops >15% from baseline
    scorer_model: str = "gemini-3.8-flash"
    response_field: str = "response"  # field in API response containing the answer
    timeout: int = 30  # seconds per request
    name: str = "AI Healthcheck"


def load_config(path: str | Path) -> HealthcheckConfig:
    """Load healthcheck config from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    tests = []
    for t in raw.get("tests", []):
        tests.append(TestCase(
            name=t["name"],
            query=t["query"],
            expect=t.get("expect", {}),
            method=t.get("method", "POST"),
            headers=t.get("headers", {}),
            body_template=t.get("body_template"),
        ))

    return HealthcheckConfig(
        endpoint=raw["endpoint"],
        tests=tests,
        schedule=raw.get("schedule", "manual"),
        alert_threshold=raw.get("alert_threshold", 0.15),
        scorer_model=raw.get("scorer_model", "gemini-3.8-flash"),
        response_field=raw.get("response_field", "response"),
        timeout=raw.get("timeout", 30),
        name=raw.get("name", "AI Healthcheck"),
    )
