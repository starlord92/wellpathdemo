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
    """If GOOGLE_APPLICATION_CREDENTIALS_JSON is set, write to /tmp and set ADC. Returns None on success, error string on failure."""
    key_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    if not key_json:
        return "GOOGLE_APPLICATION_CREDENTIALS_JSON is not set. In Vercel → Settings → Environment Variables, add it with the full service account JSON (paste the entire key file)."
    try:
        json.loads(key_json)
    except json.JSONDecodeError as e:
        return "GOOGLE_APPLICATION_CREDENTIALS_JSON is not valid JSON (maybe truncated?). Re-paste the full key. " + str(e)
    try:
        path = "/tmp/gcp-creds.json"
        with open(path, "w") as f:
            f.write(key_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        return None
    except Exception as e:
        return "Could not write credentials file: " + str(e)


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
        err = _setup_gcp_credentials()
        if err:
            _send_headers(self, 500)
            self.wfile.write(json.dumps({"error": err}).encode("utf-8"))
            return

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
