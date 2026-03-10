"""
Vercel serverless function: POST /api/extract-document (multipart: file = PDF)
Requires GOOGLE_APPLICATION_CREDENTIALS_JSON, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_BUCKET.
"""
import json
import os
import sys
from io import BytesIO

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_api = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
if _api not in sys.path:
    sys.path.insert(0, _api)

# Shared multipart parser (works on Vercel where cgi can fail)
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
        path = "/tmp/gcp-creds-doc.json"
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


def _parse_multipart(content_type, body):
    """Parse multipart/form-data and return (file_bytes, filename) or (None, None)."""
    if _parse_mp:
        out = _parse_mp(content_type, body, ("file", "document"))
        if out[0] is not None:
            return out
    try:
        import cgi
        env = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type or "",
            "CONTENT_LENGTH": str(len(body)),
        }
        fs = cgi.FieldStorage(fp=BytesIO(body), environ=env, keep_blank_values=True)
        for name in ("file", "document"):
            field = fs.get(name)
            if field and getattr(field, "file", None):
                data = field.file.read()
                fn = getattr(field, "filename", "upload.pdf") or "upload.pdf"
                if data:
                    return data, fn
        return None, None
    except Exception:
        return None, None


def _get_request_body(handler):
    """Read POST body; Vercel may send Content-Length in different casing or not at all."""
    length = 0
    for key in ("Content-Length", "content-length"):
        try:
            length = int(handler.headers.get(key, 0) or 0)
            break
        except (TypeError, ValueError):
            pass
    if length > 0:
        body = handler.rfile.read(length)
        if body:
            return body
    # Vercel sometimes doesn't pass body via rfile; try reading remainder (up to 6MB)
    try:
        rest = handler.rfile.read(6 * 1024 * 1024)
        if rest:
            return rest
    except Exception:
        pass
    return b""


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        _send_headers(self, 204)

    def do_POST(self):
        try:
            body = _get_request_body(self)
            content_type = (self.headers.get("Content-Type") or self.headers.get("content-type") or "").strip().lower()
            file_bytes = None
            filename = "upload.pdf"

            # Optional: JSON body with "url" (works on Vercel where multipart body may be missing)
            if content_type and "application/json" in content_type and body:
                try:
                    data = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
                    url = isinstance(data, dict) and (data.get("url") or "").strip()
                    if url and url.startswith("http"):
                        import urllib.request
                        req = urllib.request.Request(url, headers={"User-Agent": "EHR-Converter/1.0"})
                        with urllib.request.urlopen(req, timeout=60) as resp:
                            file_bytes = resp.read()
                        cd = resp.headers.get("Content-Disposition") or resp.headers.get("content-disposition") or ""
                        if "filename=" in cd:
                            import re as _re
                            m = _re.search(r"filename\s*=\s*[\"']?([^\"'\s;]+)", cd, _re.I)
                            if m:
                                filename = m.group(1).strip()
                        if not filename or filename == "upload.pdf":
                            from urllib.parse import urlparse
                            p = urlparse(url)
                            name = (p.path or "").strip("/").split("/")[-1]
                            if name and "." in name:
                                filename = name
                except Exception as e:
                    _send_headers(self, 400)
                    self.wfile.write(json.dumps({"error": "Invalid or unreachable URL: " + str(e)}).encode("utf-8"))
                    return

            if not file_bytes:
                file_bytes, filename = _parse_multipart(content_type, body)
            if not file_bytes:
                _send_headers(self, 400)
                diag = ""
                if not body and content_type and "multipart" in content_type:
                    diag = " Use the URL option: upload your file to a public URL (e.g. Vercel Blob, imgur) and POST JSON {\"url\": \"https://...\"}."
                self.wfile.write(json.dumps({"error": "Missing file. Send multipart with 'file' or 'document', or JSON {\"url\": \"https://...\"}." + diag}).encode("utf-8"))
                return

            tmp_path = os.path.join("/tmp", filename or "upload.pdf")
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
                result = converter.extract_from_document(tmp_path, mime_type="application/pdf", upload_to_gcs=True)
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
