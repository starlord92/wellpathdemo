"""
Vercel serverless proxy: POST /api/grants/v1/api/search2
Forwards requests to https://api.grants.gov/v1/api/search2 and returns JSON.
"""
import json
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen

TARGET_URL = "https://api.grants.gov/v1/api/search2"


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }


def _send_headers(self, status_code=200):
    self.send_response(status_code)
    for k, v in _cors_headers().items():
        self.send_header(k, v)
    self.end_headers()


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _send_headers(self, 204)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except Exception:
            length = 0
        body = self.rfile.read(length) if length > 0 else b"{}"

        try:
            req = Request(
                TARGET_URL,
                data=body,
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "grants-rfp-agent-proxy/1.0"},
            )
            with urlopen(req, timeout=60) as resp:
                payload = resp.read()
                status = getattr(resp, "status", 200)
        except Exception as e:
            _send_headers(self, 500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        _send_headers(self, status)
        self.wfile.write(payload)
