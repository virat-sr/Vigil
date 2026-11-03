"""Tiny RAG app — a FastAPI server that answers questions using Gemini + context docs.

This simulates a real production AI endpoint. Vigil tests it from the outside.

Usage:
    python demo/rag_app.py                              # Good model (gemini-3.8-flash)
    python demo/rag_app.py --model gemini-flash-lite-latest     # Cheap model (quality drops)
    python demo/rag_app.py --model gemini-3.8-flash --corrupt-context  # Corrupted docs
"""

import argparse
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

from google import genai

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
# Company FAQ
Q: What do you sell? A: Various products and services.
Q: How do I contact you? A: Visit our website.
"""


class RAGHandler(BaseHTTPRequestHandler):
    model_name = "gemini-3.8-flash"
    context = COMPANY_DOCS

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}
        query = body.get("message", "")

        try:
            resp = self.__class__._client.models.generate_content(
                model=self.model_name,
                contents=f"""You are Acme Corp's customer support assistant. Answer the user's question
using ONLY the following company documentation. Be specific, include numbers and details.
If the answer isn't in the docs, say "I don't have information about that."

## Company Documentation
{self.context}

## User Question
{query}

Answer:"""
            )
            answer = resp.text
        except Exception as e:
            answer = f"Sorry, I encountered an error: {e}"

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"response": answer}).encode())

    def log_message(self, format, *args):
        print(f"  [{self.log_date_time_string()}] {args[0]}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Demo RAG app for testing Vigil")
    parser.add_argument("--port", type=int, default=8500)
    parser.add_argument("--model", default="gemini-3.8-flash",
                        help="Gemini model to use (swap to cheaper model to simulate degradation)")
    parser.add_argument("--corrupt-context", action="store_true",
                        help="Use corrupted/outdated docs instead of real knowledge base")
    args = parser.parse_args()

    RAGHandler._client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
    RAGHandler.model_name = args.model
    RAGHandler.context = CORRUPTED_DOCS if args.corrupt_context else COMPANY_DOCS

    server = HTTPServer(("localhost", args.port), RAGHandler)
    print(f"\n  Acme Corp RAG App")
    print(f"  Model:    {args.model}")
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
