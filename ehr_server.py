"""
EHR Conversion web app server.
Serves the static hub + EHR app and provides /api/extract-text, extract-document, extract-voice, extract-image.

Run from project root:
  source .venv/bin/activate
  python ehr_server.py

Then open http://localhost:5000 and sign in; go to Hub -> EHR Conversion.
"""
import os
import sys
import tempfile

# Ensure we can import ehr_conversion from current dir
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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


def _file_upload_route(field_names, run_extract):
    """Helper: get uploaded file from request, save to temp file, call run_extract(path), then delete temp file."""
    f = None
    for name in field_names:
        f = request.files.get(name)
        if f and f.filename:
            break
    if not f or not f.filename:
        return jsonify({"error": "Missing file. Send multipart with one of: " + ", ".join(field_names)}), 400
    suffix = os.path.splitext(f.filename)[1] or ".bin"
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
    """Extract structured EHR from uploaded PDF."""
    def run(path):
        from ehr_conversion import EHRConverter
        converter = EHRConverter(project=GCP_PROJECT, bucket=GCP_BUCKET)
        return converter.extract_from_document(path, mime_type="application/pdf", upload_to_gcs=True)
    return _file_upload_route(("file", "document"), run)


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
    return _file_upload_route(("file", "audio", "voice"), run)


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
    return _file_upload_route(("file", "image"), run)


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
