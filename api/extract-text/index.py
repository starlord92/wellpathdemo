"""
Vercel serverless function: POST /api/extract-text
Uses ehr_conversion to extract structured EHR from text. Always on when deployed.

Required in Vercel env:
  GOOGLE_APPLICATION_CREDENTIALS_JSON = full JSON key of a GCP service account (so Vertex AI can auth)
Optional:
  GOOGLE_CLOUD_PROJECT (default: penfield-ai-dev), GOOGLE_CLOUD_BUCKET (default: penfield-dev)
"""
import json
import os
import sys

# Import ehr_conversion from project root (parent of api/)
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)


def _setup_gcp_credentials():
    """If GOOGLE_APPLICATION_CREDENTIALS_JSON is set, write to /tmp and set ADC."""
    key_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    if not key_json:
        return
    try:
        # Validate it's JSON
        json.loads(key_json)
        path = "/tmp/gcp-creds.json"
        with open(path, "w") as f:
            f.write(key_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
    except Exception:
        pass


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
        _setup_gcp_credentials()

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
