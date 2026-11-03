"""Mock RAG API server for testing vigil.

Simulates a real AI endpoint that answers questions.
Can be configured to "degrade" quality to test drift detection.

Run: python examples/mock_api_server.py
     python examples/mock_api_server.py --degrade   # simulate degradation
"""

import argparse
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

GOOD_RESPONSES = {
    "what is your return policy?": "Our return policy allows returns within 30 days of purchase for a full refund. Items must be in original condition.",
    "what are your business hours?": "We are open Monday to Friday, 9:00 AM to 6:00 PM EST. Saturday hours are 10:00 AM to 4:00 PM.",
    "compare the pro and enterprise plans": "The Pro plan costs $49/month and includes 10 users, 50GB storage, and email support. The Enterprise plan is $199/month with unlimited users, 500GB storage, priority support, SSO, and audit logs. Enterprise also includes a dedicated account manager and 99.99% SLA.",
    "": "I'd be happy to help! Could you please provide more details about what you're looking for?",
}

DEGRADED_RESPONSES = {
    "what is your return policy?": "We have a return policy.",  # missing key details
    "what are your business hours?": "We are open during business hours.",  # no numbers
    "compare the pro and enterprise plans": "Both plans are great options.",  # no substance
    "": "Error processing request.",  # bad error handling
}


class MockAPIHandler(BaseHTTPRequestHandler):
    degrade = False

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}

        query = body.get("message", "").lower().strip()
        responses = DEGRADED_RESPONSES if self.degrade else GOOD_RESPONSES

        response = responses.get(query)
        if response is None:
            # Default response for unknown queries
            if self.degrade:
                response = "I don't know."
            else:
                response = f"Based on our documentation, regarding '{query}': I can help with that. Please check our help center for detailed information."

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"response": response}).encode())

    def log_message(self, format, *args):
        print(f"  [{self.log_date_time_string()}] {args[0]}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--degrade", action="store_true", help="Simulate degraded quality")
    args = parser.parse_args()

    MockAPIHandler.degrade = args.degrade
    server = HTTPServer(("localhost", args.port), MockAPIHandler)

    mode = "DEGRADED" if args.degrade else "NORMAL"
    print(f"\n  Mock AI API running on http://localhost:{args.port} [{mode} mode]")
    print(f"  Press Ctrl+C to stop\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
