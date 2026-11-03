"""Scorer — LLM-as-judge scoring. Supports OpenAI and Gemini. Auto-detects based on available key."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from .config import TestCase
from .runner import TestResult


JUDGE_PROMPT = """You are an AI quality judge. Score the following AI response on a scale of 0.0 to 1.0.

## Query
{query}

## AI Response
{response}

## Expectations
{expectations}

## Scoring Criteria
- 1.0 = Perfect response, meets all expectations
- 0.8 = Good response, meets most expectations, minor issues
- 0.6 = Acceptable response, meets some expectations
- 0.4 = Poor response, misses important expectations
- 0.2 = Bad response, mostly wrong or irrelevant
- 0.0 = No response, completely wrong, or error

## Rules
- If expectations include "contains" keywords, check if they appear in the response
- If expectations include "no_hallucination", check if the response makes unsupported claims
- If expectations include "tone", check if the response matches the expected tone
- If expectations include "grounded_in_context", check if claims are supported
- If expectations include "min_length", check response length
- If expectations include "language", check if response is in the correct language

Respond with ONLY a JSON object:
{{"score": <float 0.0-1.0>, "reasoning": "<one sentence explaining the score>"}}
"""


@dataclass
class ScoreResult:
    """Score from the LLM judge."""

    test_name: str
    score: float  # 0.0 to 1.0
    reasoning: str
    latency_ms: float  # of the AI endpoint, not the judge
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.score >= 0.7 and self.error is None


def _format_expectations(expect: dict) -> str:
    """Format expectations dict into readable text for the judge."""
    if not expect:
        return "No specific expectations. Judge on general quality, relevance, and correctness."
    lines = []
    for key, val in expect.items():
        if key == "contains":
            lines.append(f"- Response MUST contain these keywords/phrases: {val}")
        elif key == "no_hallucination":
            lines.append("- Response must NOT contain hallucinated or made-up information")
        elif key == "tone":
            lines.append(f"- Response tone should be: {val}")
        elif key == "grounded_in_context":
            lines.append("- All claims must be grounded in retrieved context")
        elif key == "min_length":
            lines.append(f"- Response must be at least {val} characters long")
        elif key == "language":
            lines.append(f"- Response must be in language: {val}")
        elif key == "contains_numbers":
            lines.append("- Response must contain specific numbers/data")
        else:
            lines.append(f"- {key}: {val}")
    return "\n".join(lines)


# ── Provider-specific judge calls ───────────────────────────────

def _call_openai_judge(prompt: str, model: str) -> dict:
    """Call OpenAI as LLM judge."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(resp.choices[0].message.content)


def _call_gemini_judge(prompt: str, model: str) -> dict:
    """Call Gemini as LLM judge."""
    from google import genai as _genai
    client = _genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return json.loads(resp.text)


def _detect_provider(model: str) -> str:
    """Auto-detect which provider to use based on model name and available keys."""
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    google_key = os.environ.get("GOOGLE_API_KEY", "")

    # Explicit model name detection
    if model.startswith("gpt-") or model.startswith("o1") or model.startswith("o3"):
        if openai_key:
            return "openai"
    if model.startswith("gemini"):
        if google_key:
            return "gemini"

    # Fallback: use whichever key is available (prefer OpenAI)
    if openai_key:
        return "openai"
    if google_key:
        return "gemini"
    return "none"


# Default models per provider
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-3.8-flash",
}


def score_result(test_result: TestResult, model: str = "") -> ScoreResult:
    """Score a test result using LLM-as-judge. Auto-detects OpenAI or Gemini."""
    if test_result.error:
        return ScoreResult(
            test_name=test_result.test.name,
            score=0.0,
            reasoning=f"Endpoint error: {test_result.error}",
            latency_ms=test_result.latency_ms,
            error=test_result.error,
        )

    provider = _detect_provider(model)
    if provider == "none":
        return _rule_based_score(test_result)

    # Use default model if none specified or if model doesn't match provider
    if not model or (provider == "openai" and model.startswith("gemini")) or (provider == "gemini" and model.startswith("gpt")):
        model = DEFAULT_MODELS[provider]

    prompt = JUDGE_PROMPT.format(
        query=test_result.test.query,
        response=test_result.response_text[:3000],
        expectations=_format_expectations(test_result.test.expect),
    )

    try:
        if provider == "openai":
            data = _call_openai_judge(prompt, model)
        else:
            data = _call_gemini_judge(prompt, model)

        return ScoreResult(
            test_name=test_result.test.name,
            score=float(data.get("score", 0.0)),
            reasoning=data.get("reasoning", "No reasoning provided"),
            latency_ms=test_result.latency_ms,
        )
    except Exception as e:
        fallback = _rule_based_score(test_result)
        fallback.reasoning = f"LLM judge failed ({type(e).__name__}: {e}), rule-based: {fallback.reasoning}"
        return fallback


def _rule_based_score(result: TestResult) -> ScoreResult:
    """Score using only deterministic rules — no LLM needed. Used as fallback."""
    expect = result.test.expect
    response = result.response_text
    checks_passed = 0
    checks_total = 0
    reasons = []

    if not response or not response.strip():
        return ScoreResult(
            test_name=result.test.name, score=0.0,
            reasoning="Empty response", latency_ms=result.latency_ms,
        )

    if "contains" in expect:
        checks_total += 1
        keywords = expect["contains"]
        missing = [kw for kw in keywords if kw.lower() not in response.lower()]
        if not missing:
            checks_passed += 1
            reasons.append("all keywords found")
        else:
            reasons.append(f"missing keywords: {missing}")

    if "min_length" in expect:
        checks_total += 1
        if len(response) >= expect["min_length"]:
            checks_passed += 1
            reasons.append(f"length OK ({len(response)} chars)")
        else:
            reasons.append(f"too short ({len(response)}/{expect['min_length']})")

    if "contains_numbers" in expect and expect["contains_numbers"]:
        checks_total += 1
        import re
        if re.search(r"\d+", response):
            checks_passed += 1
            reasons.append("contains numbers")
        else:
            reasons.append("no numbers found")

    if checks_total == 0:
        score = 0.7 if len(response) > 20 else 0.4
        return ScoreResult(
            test_name=result.test.name, score=score,
            reasoning=f"Rule-based: response exists ({len(response)} chars)",
            latency_ms=result.latency_ms,
        )

    score = round(checks_passed / checks_total, 2)
    return ScoreResult(
        test_name=result.test.name, score=score,
        reasoning=f"Rule-based: {'; '.join(reasons)}",
        latency_ms=result.latency_ms,
    )


def score_all(test_results: list[TestResult], model: str = "") -> list[ScoreResult]:
    """Score all test results. Auto-detects provider from env vars and model name."""
    return [score_result(tr, model) for tr in test_results]
