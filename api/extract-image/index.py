"""
Vercel serverless: POST /api/extract-image (multipart: file = image)
Extracts text from image then structured EHR from that text.
"""
import json
import os
import sys
from io import BytesIO
from http.server import BaseHTTPRequestHandler

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_api = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
if _api not in sys.path:
    sys.path.insert(0, _api)
try:
    from _multipart import parse_multipart as _parse_mp
except Exception:
    _parse_mp = None


def _setup_gcp_credentials():
    """Write GOOGLE_APPLICATION_CREDENTIALS_JSON to /tmp and set env. Returns None on success, error string on failure."""
    key_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    if not key_json:
        return "GOOGLE_APPLICATION_CREDENTIALS_JSON is not set. In Vercel → Settings → Environment Variables, add it with the full service account JSON (paste the entire key file)."
    try:
        json.loads(key_json)
    except json.JSONDecodeError as e:
        return "GOOGLE_APPLICATION_CREDENTIALS_JSON is not valid JSON (maybe truncated?). Re-paste the full key. " + str(e)
    try:
        path = "/tmp/gcp-creds-image.json"
        with open(path, "w") as f:
            f.write(key_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        return None
    except Exception as e:
        return "Could not write credentials file: " + str(e)


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


def _get_request_body(handler):
    length = 0
    for key in ("Content-Length", "content-length"):
        try:
            length = int(handler.headers.get(key, 0) or 0)
            break
        except (TypeError, ValueError):
            pass
    return handler.rfile.read(length) if length > 0 else b""

def _parse_multipart(content_type, body):
    if _parse_mp:
        out = _parse_mp(content_type, body, ("file", "image", "document"))
        if out[0] is not None:
            return out
    try:
        import cgi
        env = {"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type or "", "CONTENT_LENGTH": str(len(body))}
        fs = cgi.FieldStorage(fp=BytesIO(body), environ=env, keep_blank_values=True)
        for name in ("file", "image", "document"):
            field = fs.get(name)
            if field and getattr(field, "file", None):
                data = field.file.read()
                fn = getattr(field, "filename", "upload.jpg") or "upload.jpg"
                if data:
                    return data, fn
        return None, None
    except Exception:
        return None, None


def _mime_for_filename(filename):
    if not filename:
        return "image/jpeg"
    lower = filename.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _send_headers(self, 204)

    def do_POST(self):
        try:
            body = _get_request_body(self)
            content_type = self.headers.get("Content-Type") or self.headers.get("content-type") or ""
            file_bytes, filename = _parse_multipart(content_type, body)
            if not file_bytes:
                _send_headers(self, 400)
                self.wfile.write(json.dumps({"error": "Missing file. Send multipart with 'file' or 'image'."}).encode("utf-8"))
                return

            tmp_path = os.path.join("/tmp", filename or "upload.jpg")
            try:
                with open(tmp_path, "wb") as f:
                    f.write(file_bytes)
            except Exception as e:
                _send_headers(self, 500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
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
                mime = _mime_for_filename(filename)
                text = converter.extract_text_from_image(tmp_path, mime_type=mime, upload_to_gcs=True)
                if not (text and text.strip()):
                    result = {"extracted_text": "", "structured": {}}
                else:
                    result = converter.extract_from_text(text)
                    result["extracted_text"] = text
                out = json.dumps(result).encode("utf-8")
            except Exception as e:
                _send_headers(self, 500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

            _send_headers(self, 200)
            self.wfile.write(out)
        except Exception as e:
            _send_headers(self, 500)
            self.wfile.write(json.dumps({"error": "Server error: " + str(e)}).encode("utf-8"))
