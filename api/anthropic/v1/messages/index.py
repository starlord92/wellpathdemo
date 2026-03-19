"""
Vercel serverless proxy: POST /api/anthropic/v1/messages
Forwards requests to Anthropic Messages API using server-side key.

Required env var:
  ANTHROPIC_API_KEY=sk-ant-...
"""
import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen

TARGET_URL = "https://api.anthropic.com/v1/messages"


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
        api_key = (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("VITE_ANTHROPIC_API_KEY") or "").strip()
        if not api_key or not api_key.startswith("sk-ant-"):
            _send_headers(self, 500)
            self.wfile.write(json.dumps({"error": "Missing or invalid ANTHROPIC_API_KEY in environment."}).encode("utf-8"))
            return

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
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "User-Agent": "grants-rfp-agent-proxy/1.0",
                },
            )
            with urlopen(req, timeout=90) as resp:
                payload = resp.read()
                status = getattr(resp, "status", 200)
        except Exception as e:
            _send_headers(self, 500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        _send_headers(self, status)
        self.wfile.write(payload)
