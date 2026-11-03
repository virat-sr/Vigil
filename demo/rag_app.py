"""Tiny RAG app — answers questions using an LLM + company docs.

Supports OpenRouter (any model), OpenAI, or Gemini — auto-detects from env.

Usage:
    python demo/rag_app.py                                         # auto-detect provider
    python demo/rag_app.py --model openai/gpt-4o-mini              # OpenRouter model
    python demo/rag_app.py --model meta-llama/llama-3-8b-instruct  # free model (worse)
    python demo/rag_app.py --corrupt-context                       # bad docs
"""

import argparse
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Company knowledge base (simulates retrieved docs) ───────────

COMPANY_DOCS = """
# Acme Corp — Internal Knowledge Base

## Return Policy
Customers may return any product within 30 days of purchase for a full refund.
Items must be in original packaging and unused condition. Refunds are processed
within 5-7 business days to the original payment method. Digital products are
non-refundable after download.

## Pricing Plans
- **Starter**: $19/month — 5 users, 10GB storage, email support
- **Pro**: $49/month — 25 users, 100GB storage, priority email + chat support
- **Enterprise**: $199/month — unlimited users, 1TB storage, 24/7 phone support,
  dedicated account manager, SSO, audit logs, 99.99% SLA

## Business Hours
Monday to Friday: 9:00 AM - 6:00 PM Eastern Time
Saturday: 10:00 AM - 4:00 PM Eastern Time
Sunday: Closed
Holiday hours may vary — check our website for updates.

## Technical Support
- Starter: Email support, 48-hour response time
- Pro: Email + live chat, 4-hour response time during business hours
- Enterprise: 24/7 phone + email + chat, 1-hour response time, dedicated engineer

## Security & Compliance
All data is encrypted at rest (AES-256) and in transit (TLS 1.3).
SOC 2 Type II certified. GDPR compliant. Annual penetration testing.
Enterprise plan includes HIPAA BAA upon request.
"""

CORRUPTED_DOCS = """
# Acme Corp — Knowledge Base
(Last verified: 2023 — some sections may be outdated)

## Return Policy
Customers can return products within 14 days of purchase. A $5.99 restocking fee
applies to all returns. Items must be unopened. Refunds take 15-20 business days.
(NOTE: This section was last updated in 2023 — pricing team changed some numbers
but the doc wasn't fully reviewed.)

## Pricing Plans
- **Starter**: $29/month — 3 users, 5GB storage, email support
- **Pro**: $79/month — 15 users, 50GB storage, email + chat support
- **Enterprise**: Contact sales for pricing
(NOTE: These prices are from Q1 2023. Marketing may have updated them since.)

## Business Hours
Monday to Friday: 9:00 AM - 5:00 PM Eastern Time
Weekends: Closed

## Technical Support
All plans include email support during business hours.
Enterprise customers can request priority handling.

## Security
We take security seriously. Our infrastructure is hosted on major cloud providers.
We conduct regular security reviews.
"""

SYSTEM_PROMPT = """You are Acme Corp's customer support assistant. Answer the user's question
using ONLY the following company documentation. Be specific, include numbers and details.
If the answer isn't in the docs, say "I don't have information about that."

## Company Documentation
{context}"""


def _create_client(model: str):
    """Create the right LLM client based on available keys."""
    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    google_key = os.environ.get("GOOGLE_API_KEY", "")

    if openrouter_key:
        from openai import OpenAI
        return "openrouter", OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")
    elif openai_key:
        from openai import OpenAI
        return "openai", OpenAI(api_key=openai_key)
    elif google_key:
        from google import genai
        return "gemini", genai.Client(api_key=google_key)
    else:
        raise RuntimeError("Set OPENROUTER_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY")


class RAGHandler(BaseHTTPRequestHandler):
    model_name = "openai/gpt-4o-mini"
    context = COMPANY_DOCS
    provider = "openrouter"
    client = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}
        query = body.get("message", "")

        system = SYSTEM_PROMPT.format(context=self.context)

        import time as _time
        answer = None
        for attempt in range(3):
            try:
                if self.provider in ("openrouter", "openai"):
                    resp = self.__class__.client.chat.completions.create(
                        model=self.model_name,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": query},
                        ],
                        temperature=0,
                    )
                    answer = resp.choices[0].message.content
                else:  # gemini
                    resp = self.__class__.client.models.generate_content(
                        model=self.model_name,
                        contents=f"{system}\n\n## User Question\n{query}\n\nAnswer:",
                    )
                    answer = resp.text
                break
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    _time.sleep(2 * (attempt + 1))  # backoff: 2s, 4s
                    continue
                answer = f"Sorry, I encountered an error: {e}"
                break
        if answer is None:
            answer = "Sorry, request failed after retries."

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"response": answer}).encode())

    def log_message(self, format, *args):
        print(f"  [{self.log_date_time_string()}] {args[0]}", flush=True)


# Default models per provider
DEFAULT_MODELS = {
    "openrouter": "openai/gpt-4o-mini",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-3.8-flash",
}


def main():
    parser = argparse.ArgumentParser(description="Demo RAG app for testing Vigil")
    parser.add_argument("--port", type=int, default=8500)
    parser.add_argument("--model", default="",
                        help="Model to use (e.g. openai/gpt-4o-mini, meta-llama/llama-3-8b-instruct)")
    parser.add_argument("--corrupt-context", action="store_true",
                        help="Use corrupted/outdated docs instead of real knowledge base")
    args = parser.parse_args()

    # Load .env
    from pathlib import Path
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if v.strip() and k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()

    provider, client = _create_client(args.model)
    RAGHandler.provider = provider
    RAGHandler.client = client
    RAGHandler.model_name = args.model or DEFAULT_MODELS[provider]
    RAGHandler.context = CORRUPTED_DOCS if args.corrupt_context else COMPANY_DOCS

    server = HTTPServer(("localhost", args.port), RAGHandler)
    print(f"\n  Acme Corp RAG App")
    print(f"  Provider: {provider}")
    print(f"  Model:    {RAGHandler.model_name}")
    print(f"  Context:  {'CORRUPTED' if args.corrupt_context else 'Full knowledge base'}")
    print(f"  Running:  http://localhost:{args.port}")
    print(f"  Press Ctrl+C to stop\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
