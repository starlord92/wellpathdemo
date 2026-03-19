"""
EHR Conversion web app server.
Serves the static hub + EHR app and provides /api/extract-text, extract-document, extract-voice, extract-image.

Run from project root:
  source .venv/bin/activate
  python ehr_server.py

Then open http://localhost:5000 and sign in; go to Hub -> EHR Conversion.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure we can import ehr_conversion from current dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load_simple_env_file(path):
    """Load KEY=VALUE lines from .env-like file into os.environ if missing."""
    try:
        fp = Path(path)
        if not fp.exists():
            return
        for raw in fp.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v
    except Exception:
        pass


def _setup_gcp_credentials():
    """If GOOGLE_APPLICATION_CREDENTIALS_JSON is set, write to a temp file and set ADC."""
    key_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON", "").strip()
    if not key_json:
        return
    try:
        import tempfile
        json.loads(key_json)
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write(key_json)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
    except Exception:
        pass


# Load Anthropic env from common local locations
_load_simple_env_file("/Users/sumanth/Downloads/grants-rfp-agent/.env.local")
_load_simple_env_file(".env.local")

_setup_gcp_credentials()

from flask import Flask, request, jsonify, send_from_directory, send_file

app = Flask(__name__, static_folder=".", static_url_path="")

# GCP project and bucket (defaults: penfield-ai-dev, penfield-dev)
GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "penfield-ai-dev")
GCP_BUCKET = os.environ.get("GOOGLE_CLOUD_BUCKET", "penfield-dev")


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/api/extract-text", methods=["POST"])
def extract_text():
    """Extract structured EHR/PII from plain text. Requires GOOGLE_CLOUD_PROJECT."""
    if not GCP_PROJECT:
        return jsonify({"error": "GOOGLE_CLOUD_PROJECT is not set. Set it and restart the server."}), 500
    try:
        data = request.get_json(force=True, silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "Missing or empty 'text' in request body."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    try:
        from ehr_conversion import EHRConverter
        converter = EHRConverter(project=GCP_PROJECT, bucket=GCP_BUCKET)
        result = converter.extract_from_text(text)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _fetch_url_to_path(url, default_suffix=".bin"):
    """Fetch URL to a temp file; return (path, suffix) or raise."""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "EHR-Converter/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    cd = resp.headers.get("Content-Disposition") or ""
    filename = "upload" + default_suffix
    if "filename=" in cd:
        import re
        m = re.search(r"filename\s*=\s*[\"']?([^\"'\s;]+)", cd, re.I)
        if m:
            filename = m.group(1).strip()
    if filename == "upload" + default_suffix and url:
        from urllib.parse import urlparse
        name = (urlparse(url).path or "").strip("/").split("/")[-1]
        if name and "." in name:
            filename = name
    suffix = os.path.splitext(filename)[1] or default_suffix
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
    return path


def _file_upload_route(field_names, run_extract, default_suffix=".bin"):
    """Helper: JSON url or multipart file -> temp file -> run_extract(path)."""
    if request.content_type and "application/json" in request.content_type:
        try:
            data = request.get_json(force=True, silent=True) or {}
            url = (data.get("url") or "").strip()
            if url and url.startswith("http"):
                path = _fetch_url_to_path(url, default_suffix)
                try:
                    return jsonify(run_extract(path))
                finally:
                    try:
                        os.unlink(path)
                    except Exception:
                        pass
        except Exception as e:
            return jsonify({"error": "Invalid or unreachable URL: " + str(e)}), 400

    f = None
    for name in field_names:
        f = request.files.get(name)
        if f and f.filename:
            break
    if not f or not f.filename:
        return jsonify({"error": "Missing file. Send multipart with one of: " + ", ".join(field_names) + ', or JSON {"url": "https://..."}'}), 400
    suffix = os.path.splitext(f.filename)[1] or default_suffix
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(f.read())
        return jsonify(run_extract(path))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


@app.route("/api/extract-document", methods=["POST"])
def extract_document():
    """Extract structured EHR from uploaded PDF or from URL."""
    def run(path):
        from ehr_conversion import EHRConverter
        converter = EHRConverter(project=GCP_PROJECT, bucket=GCP_BUCKET)
        return converter.extract_from_document(path, mime_type="application/pdf", upload_to_gcs=True)
    return _file_upload_route(("file", "document"), run, ".pdf")


@app.route("/api/extract-voice", methods=["POST"])
def extract_voice():
    """Transcribe audio and extract structured EHR from the transcription."""
    def run(path):
        from ehr_conversion import EHRConverter
        converter = EHRConverter(project=GCP_PROJECT, bucket=GCP_BUCKET)
        ext = os.path.splitext(path)[1].lower()
        mime = "audio/wav" if ext == ".wav" else "audio/mpeg"
        if ext in (".m4a", ".mp4"):
            mime = "audio/mp4"
        elif ext == ".webm":
            mime = "audio/webm"
        return converter.extract_from_audio(path, mime_type=mime, upload_to_gcs=True)
    return _file_upload_route(("file", "audio", "voice"), run, ".mp3")


@app.route("/api/extract-image", methods=["POST"])
def extract_image():
    """Extract text from image then structured EHR from that text."""
    def run(path):
        from ehr_conversion import EHRConverter
        converter = EHRConverter(project=GCP_PROJECT, bucket=GCP_BUCKET)
        ext = os.path.splitext(path)[1].lower()
        mime = "image/jpeg"
        if ext == ".png":
            mime = "image/png"
        elif ext == ".gif":
            mime = "image/gif"
        elif ext == ".webp":
            mime = "image/webp"
        text = converter.extract_text_from_image(path, mime_type=mime, upload_to_gcs=True)
        if not (text and text.strip()):
            return {"extracted_text": "", "structured": {}}
        result = converter.extract_from_text(text)
        result["extracted_text"] = text
        return result
    return _file_upload_route(("file", "image"), run, ".jpg")


@app.route("/api/grants/v1/api/search2", methods=["POST"])
def grants_search_proxy():
    """Local proxy to Grants.gov search API for grants-rfp-agent."""
    import urllib.request

    payload = request.get_json(force=True, silent=True) or {}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.grants.gov/v1/api/search2",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "grants-rfp-agent-local/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            return app.response_class(text, status=getattr(resp, "status", 200), mimetype="application/json")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/anthropic/v1/messages", methods=["POST"])
def anthropic_messages_proxy():
    """Local proxy to Anthropic messages API for grants-rfp-agent."""
    import urllib.request

    api_key = (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("VITE_ANTHROPIC_API_KEY") or "").strip()
    if not api_key or not api_key.startswith("sk-ant-"):
        return jsonify({"error": "Missing or invalid ANTHROPIC_API_KEY (or VITE_ANTHROPIC_API_KEY)."}), 500

    payload = request.get_json(force=True, silent=True) or {}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "grants-rfp-agent-local/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            return app.response_class(text, status=getattr(resp, "status", 200), mimetype="application/json")
    except Exception as e:
        # bubble more detail (e.g., auth/limit errors from Anthropic)
        try:
            import urllib.error
            if isinstance(e, urllib.error.HTTPError):
                detail = e.read().decode("utf-8", errors="replace")
                return app.response_class(detail or json.dumps({"error": str(e)}), status=e.code, mimetype="application/json")
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@app.route("/<path:path>")
def static_file(path):
    if path.startswith("api/"):
        return jsonify({"error": "Not found"}), 404
    if os.path.isfile(path):
        return send_from_directory(".", path)
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
