"""Runner — calls your AI endpoint with test queries and collects responses."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.request import urlopen, Request
from urllib.error import URLError

from .config import HealthcheckConfig, TestCase


@dataclass
class TestResult:
    """Raw result from calling the AI endpoint."""

    test: TestCase
    response_text: str
    status_code: int
    latency_ms: float
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None and self.status_code == 200


def run_test(test: TestCase, config: HealthcheckConfig) -> TestResult:
    """Call the AI endpoint with a single test query."""
    body = test.build_request_body()
    body_bytes = json.dumps(body).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        **test.headers,
    }

    req = Request(
        config.endpoint,
        data=body_bytes,
        headers=headers,
        method=test.method,
    )

    start = time.perf_counter()
    try:
        with urlopen(req, timeout=config.timeout) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            latency = (time.perf_counter() - start) * 1000

            # Extract the response text from the API response
            try:
                data = json.loads(raw)
                # Try configured response field, then common alternatives
                response_text = (
                    data.get(config.response_field)
                    or data.get("response")
                    or data.get("answer")
                    or data.get("content")
                    or data.get("text")
                    or data.get("message")
                    or data.get("output")
                    or raw
                )
                if isinstance(response_text, dict):
                    response_text = json.dumps(response_text)
            except json.JSONDecodeError:
                response_text = raw

            return TestResult(
                test=test,
                response_text=str(response_text),
                status_code=status,
                latency_ms=round(latency, 1),
            )

    except URLError as e:
        latency = (time.perf_counter() - start) * 1000
        return TestResult(
            test=test,
            response_text="",
            status_code=0,
            latency_ms=round(latency, 1),
            error=str(e),
        )
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return TestResult(
            test=test,
            response_text="",
            status_code=0,
            latency_ms=round(latency, 1),
            error=f"{type(e).__name__}: {e}",
        )


def run_all(config: HealthcheckConfig) -> list[TestResult]:
    """Run all test cases against the endpoint."""
    results = []
    for test in config.tests:
        result = run_test(test, config)
        results.append(result)
    return results
