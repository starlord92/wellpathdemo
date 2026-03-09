"""
Vercel serverless function: POST /api/extract-text
Uses ehr_conversion to extract structured EHR from text. Always on when deployed.
Set GOOGLE_CLOUD_PROJECT (and optionally GOOGLE_CLOUD_BUCKET) in Vercel env.
"""
import json
import os
import sys

# Import ehr_conversion from project root (parent of api/)
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

from http.server import BaseHTTPRequestHandler


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
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else "{}"
        try:
            data = json.loads(body) if body.strip() else {}
        except json.JSONDecodeError:
            _send_headers(self, 400)
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
            return

        text = (data.get("text") or "").strip()
        if not text:
            _send_headers(self, 400)
            self.wfile.write(json.dumps({"error": "Missing or empty 'text'"}).encode("utf-8"))
            return

        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "penfield-ai-dev")
        bucket = os.environ.get("GOOGLE_CLOUD_BUCKET", "penfield-dev")

        try:
            from ehr_conversion import EHRConverter
            converter = EHRConverter(project=project, bucket=bucket)
            result = converter.extract_from_text(text)
            out = json.dumps(result).encode("utf-8")
        except Exception as e:
            _send_headers(self, 500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        _send_headers(self, 200)
        self.wfile.write(out)
