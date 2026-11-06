"""Mock RAG API server for testing vigil.

Two modes:
  uv run python examples/mock_api_server.py           # good responses (detailed, accurate)
  uv run python examples/mock_api_server.py --degrade # degraded responses (partial, wrong numbers)
"""

import argparse
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# Good responses — detailed, with correct numbers and keywords
GOOD_RESPONSES = {
    "return": "Our return policy allows customers to return any product within 30 days of purchase for a full refund. Items must be in original packaging and unused condition. Refunds are processed within 5-7 business days to the original payment method. Digital products are non-refundable after download.",
    "pricing": "We offer three plans: Starter at $19/month with 5 users and 10GB storage, Pro at $49/month with 25 users and 100GB storage plus priority chat support, and Enterprise at $199/month with unlimited users, 1TB storage, 24/7 phone support, dedicated account manager, SSO, audit logs, and a 99.99% SLA.",
    "hour": "We are open Monday to Friday from 9:00 AM to 6:00 PM Eastern Time. Saturday hours are 10:00 AM to 4:00 PM. We are closed on Sunday. Holiday hours may vary.",
    "security": "We hold SOC 2 Type II certification and are fully GDPR compliant. All data is encrypted at rest using AES-256 and in transit using TLS 1.3. We conduct annual penetration testing. Enterprise plan includes HIPAA BAA upon request.",
    "enterprise": "Enterprise has several features that Pro doesn't include: SSO (single sign-on), audit logs, a dedicated account manager, 24/7 phone support with 1-hour response time, a 99.99% SLA guarantee, and HIPAA BAA availability. Pro only includes email and chat support with 4-hour response time.",
    "support": "Enterprise support includes 24/7 phone, email, and chat with a guaranteed 1-hour response time and a dedicated support engineer. Pro includes email and live chat with 4-hour response time during business hours. Starter is email-only with 48-hour response time.",
}

# Degraded responses — partially wrong, missing key details, wrong numbers
DEGRADED_RESPONSES = {
    "return": "We accept returns within 14 days of purchase. A $5.99 restocking fee applies. Items must be unopened. Refunds are processed within 15-20 business days.",
    "pricing": "We have a Starter plan at $29/month for 3 users, Pro at $79/month for 15 users, and Enterprise which requires contacting our sales team for custom pricing.",
    "hour": "Our offices are open Monday through Friday, 9:00 AM to 5:00 PM Eastern Time. We are closed on weekends.",
    "security": "We take security seriously and use industry-standard encryption. Our infrastructure is hosted on major cloud providers and we conduct regular security reviews.",
    "enterprise": "Enterprise customers get priority support and additional storage. Contact our sales team for details on Enterprise-specific features and pricing.",
    "support": "All plans include email support during business hours. Enterprise customers can request priority handling for urgent issues.",
}

DEFAULT_GOOD = "Based on our documentation, I can help with that. Our company offers comprehensive products and services. For detailed information about specific topics, please check our help center or contact our support team."
DEFAULT_DEGRADED = "I don't have specific information about that. Please contact our support team or check our website."


def _match_response(query, responses, default):
    """Fuzzy match query to response keys."""
    query_lower = query.lower()
    for key, response in responses.items():
        if key in query_lower:
            return response
    return default


class MockAPIHandler(BaseHTTPRequestHandler):
    degrade = False

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}
        query = body.get("message", "")

        if self.degrade:
            response = _match_response(query, DEGRADED_RESPONSES, DEFAULT_DEGRADED)
        else:
            response = _match_response(query, GOOD_RESPONSES, DEFAULT_GOOD)

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"response": response}).encode())

    def log_message(self, format, *args):
        print(f"  [{self.log_date_time_string()}] {args[0]}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8500)
    parser.add_argument("--degrade", action="store_true")
    args = parser.parse_args()

    MockAPIHandler.degrade = args.degrade
    server = HTTPServer(("localhost", args.port), MockAPIHandler)
    mode = "DEGRADED" if args.degrade else "NORMAL"
    print(f"\n  Mock AI API on http://localhost:{args.port} [{mode}]")
    print(f"  Ctrl+C to stop\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
