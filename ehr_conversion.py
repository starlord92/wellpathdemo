"""
Reusable unstructured → structured EHR conversion logic.

Use this module from another application (different web app, API, or script)
without running the full chatui Flask app.

Requirements:
  - Python 3.9+
  - Set GOOGLE_CLOUD_PROJECT (or pass project to init)
  - Install: pip install google-cloud-storage google-cloud-aiplatform

Usage from another app:

  from ehr_conversion import EHRConverter

  converter = EHRConverter(project="your-gcp-project", bucket="your-bucket")
  result = converter.extract_from_text("Jane Doe, 123 Main St, jane@example.com")
  result = converter.extract_from_document("/path/to/clinical_note.pdf")
"""

import json
import os
import re
from typing import Any, Optional

# Set default before importing Vertex (caller can override via env)
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "penfield-ai-dev")

import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
import vertexai.preview.generative_models as generative_models


# --- Prompts (same as chatui) ---
PII_SYSTEM_INSTRUCTION = """Given the sentence below containing personal information, extract all identifiable personal details and organize them meaningfully into a JSON format. Ensure that each piece of information is categorized appropriately based on its content. The output should reflect all discernible personal information from the input sentence. Make sure all dates are in dd-mm-yyyy format regardless of how they are entered.

CRITICAL: Use discrete JSON keys such as name, address, email, phone_number, organization, date_of_birth, etc. Do NOT put the entire input or a long transcript into a single field named extracted_text, transcription, raw_text, text, or similar — split facts into the appropriate fields. If a field has no value, omit it.

Output:
Return the extracted information as a JSON object only.

Example:
Input Sentence: "Jane Doe, living at 123 Maple Street, Springfield, IL 62704, works at Acme Corp and can be contacted at jane.doe@example.com or (555) 123-4567."

Output JSON:
{
    "name": "Jane Doe",
    "address": "123 Maple Street, Springfield, IL 62704",
    "organization": "Acme Corp",
    "email": "jane.doe@example.com",
    "phone_number": "(555) 123-4567"
}"""

DOCUMENT_SYSTEM_INSTRUCTION = (
    "As an expert in document entity extraction, you parse documents to identify and organize "
    "specific entities from diverse sources into structured formats, following detailed guidelines "
    "for clarity and completeness. Return all information extracted as a single JSON object with "
    "discrete keys (name, address, email, phone_number, organization, dates, identifiers, etc.). "
    "Do NOT dump the full document text into one key like extracted_text or transcription."
)

# Plain text generation (e.g. audio transcription)
TRANSCRIBE_GENERATION_CONFIG = GenerationConfig(
    max_output_tokens=8192,
    temperature=1,
    top_p=0.95,
)

# Structured JSON — reduces model returning one blob field with the whole input
STRUCTURED_JSON_GENERATION_CONFIG = GenerationConfig(
    max_output_tokens=8192,
    temperature=1,
    top_p=0.95,
    response_mime_type="application/json",
)

SAFETY_SETTINGS = {
    generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}


def _clean_json_response(raw: str) -> str:
    """Strip markdown code fences and return clean JSON string."""
    text = raw.strip()
    text = text.removeprefix("```json").removeprefix("```").strip()
    text = text.removesuffix("```").strip()
    text = re.sub(r"^json\s*\n?", "", text, flags=re.IGNORECASE).strip()
    return text.strip("`\n ")


def _collect_stream(responses) -> str:
    parts = []
    for r in responses:
        t = getattr(r, "text", None) or ""
        parts.append(t)
    return "".join(parts)


# Keys models often misuse to echo the full transcript / OCR text instead of discrete fields
_PROSE_ECHO_KEYS = frozenset(
    {
        "extracted_text",
        "raw_text",
        "transcription",
        "full_text",
        "text_content",
        "input_text",
        "original_text",
    }
)


def _dedupe_prose_keys(structured: dict[str, Any], source_text: str) -> dict[str, Any]:
    """
    Drop JSON fields that duplicate the full source string (common model mistake after voice/OCR).
    """
    if not structured:
        return {}
    src = (source_text or "").strip()
    if not src:
        return dict(structured)
    out: dict[str, Any] = {}
    for k, v in structured.items():
        if k in _PROSE_ECHO_KEYS and isinstance(v, str):
            vs = v.strip()
            if vs == src or (len(vs) > 40 and src in vs and len(vs) >= len(src) * 0.85):
                continue
        out[k] = v
    return out


def format_ehr_with_source_text(structured: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Standard shape for voice/image: transcription or OCR plus discrete structured fields."""
    if not isinstance(structured, dict):
        structured = {}
    clean = _dedupe_prose_keys(structured, source_text)
    return {
        "extracted_text": source_text,
        "structured": clean,
    }


class EHRConverter:
    """
    Unstructured → structured EHR conversion using Vertex AI (Gemini).
    """

    def __init__(
        self,
        project: Optional[str] = None,
        location: str = "us-central1",
        bucket: Optional[str] = None,
    ):
        self.project = project or os.environ.get("GOOGLE_CLOUD_PROJECT")
        self.location = location
        self.bucket_name = bucket
        self._initialized = False

    def _ensure_vertex(self) -> None:
        if not self._initialized:
            vertexai.init(project=self.project, location=self.location)
            self._initialized = True

    def extract_from_text(self, text: str) -> dict[str, Any]:
        """
        Extract structured PII/EHR from free text (e.g. one sentence or paragraph).
        Returns a dict; raises on parse error (caller can catch and use raw string).
        """
        if not (text or "").strip():
            return {"note": "No text to analyze.", "structured": {}}

        self._ensure_vertex()
        model = GenerativeModel(
            "gemini-2.0-flash-001",
            system_instruction=[PII_SYSTEM_INSTRUCTION],
        )
        responses = model.generate_content(
            [text],
            generation_config=STRUCTURED_JSON_GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            stream=True,
        )
        raw = _collect_stream(responses)
        cleaned = _clean_json_response(raw)
        if not cleaned:
            raise ValueError(
                "Model returned empty JSON. If this was from voice, transcription may be missing or blocked. "
                f"Raw preview: {(raw or '')[:400]!r}"
            )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Model output was not valid JSON ({e}). Preview: {cleaned[:500]!r}"
            ) from e

    def extract_from_document(
        self,
        source: str,
        mime_type: str = "application/pdf",
        upload_to_gcs: bool = True,
    ) -> dict[str, Any]:
        """
        Extract structured entities from a document (PDF, etc.).

        Args:
            source: Either a local file path or a gs:// URI. If local and upload_to_gcs
                    is True, file is uploaded to the configured bucket first.
            mime_type: MIME type of the document (default application/pdf).
            upload_to_gcs: If True and source is a path, upload to GCS before calling Vertex.

        Returns:
            Parsed JSON as a dict.
        """
        if not self.bucket_name and (upload_to_gcs or not source.startswith("gs://")):
            raise ValueError("bucket must be set when using a local file or upload_to_gcs=True")

        gs_uri = source
        if not source.startswith("gs://"):
            from google.cloud import storage
            client = storage.Client(project=self.project)
            bucket = client.bucket(self.bucket_name)
            blob_name = os.path.basename(source)
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(source)
            gs_uri = f"gs://{self.bucket_name}/{blob_name}"

        self._ensure_vertex()
        model = GenerativeModel(
            "gemini-2.0-flash-001",
            system_instruction=[DOCUMENT_SYSTEM_INSTRUCTION],
        )
        part = Part.from_uri(mime_type=mime_type, uri=gs_uri)
        responses = model.generate_content(
            [part, "Extract information from document and return json file"],
            generation_config=STRUCTURED_JSON_GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            stream=True,
        )
        raw = _collect_stream(responses)
        cleaned = _clean_json_response(raw)
        if not cleaned:
            raise ValueError(
                "Model returned empty JSON for document. "
                f"Raw preview: {(raw or '')[:400]!r}"
            )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Document extraction was not valid JSON ({e}). Preview: {cleaned[:500]!r}"
            ) from e

    def extract_from_audio(
        self,
        source: str,
        mime_type: str = "audio/mpeg",
        upload_to_gcs: bool = True,
    ) -> dict[str, Any]:
        """
        Transcribe audio and extract structured PII from the transcription.
        source: local path or gs:// URI (same semantics as extract_from_document).
        """
        if not self.bucket_name and (upload_to_gcs or not source.startswith("gs://")):
            raise ValueError("bucket must be set when using a local file or upload_to_gcs=True")

        gs_uri = source
        if not source.startswith("gs://"):
            from google.cloud import storage
            client = storage.Client(project=self.project)
            bucket = client.bucket(self.bucket_name)
            blob_name = os.path.basename(source)
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(source)
            gs_uri = f"gs://{self.bucket_name}/{blob_name}"

        self._ensure_vertex()
        model = GenerativeModel("gemini-2.0-flash-001")
        part = Part.from_uri(mime_type=mime_type, uri=gs_uri)
        responses = model.generate_content(
            [part, "Generate transcription from the audio, only extract speech and ignore background audio."],
            generation_config=TRANSCRIBE_GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            stream=True,
        )
        transcription = (_collect_stream(responses) or "").strip()
        if not transcription:
            return {
                "extracted_text": "",
                "structured": {},
                "note": "No speech could be transcribed from this audio. Try clearer speech, less background noise, or a supported format (MP3, WAV, M4A, WebM).",
            }

        structured = self.extract_from_text(transcription)
        if not isinstance(structured, dict):
            structured = {}
        return format_ehr_with_source_text(structured, transcription)

    def extract_text_from_image(
        self,
        source: str,
        mime_type: str = "image/jpeg",
        upload_to_gcs: bool = True,
    ) -> str:
        """
        Extract text from an image (e.g. scanned form). Returns raw text.
        source: local path or gs:// URI.
        """
        if not self.bucket_name and (upload_to_gcs or not source.startswith("gs://")):
            raise ValueError("bucket must be set when using a local file or upload_to_gcs=True")

        gs_uri = source
        if not source.startswith("gs://"):
            from google.cloud import storage
            client = storage.Client(project=self.project)
            bucket = client.bucket(self.bucket_name)
            blob_name = os.path.basename(source)
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(source)
            gs_uri = f"gs://{self.bucket_name}/{blob_name}"

        self._ensure_vertex()
        model = GenerativeModel("gemini-2.0-flash-001")
        part = Part.from_uri(mime_type=mime_type, uri=gs_uri)
        responses = model.generate_content(
            [part, "Read the text in this image."],
            generation_config=TRANSCRIBE_GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            stream=True,
        )
        return _collect_stream(responses)


# --- Convenience functions (no class) ---

def extract_from_text(text: str, project: Optional[str] = None) -> dict[str, Any]:
    """One-off: extract structured data from text using default project from env."""
    c = EHRConverter(project=project)
    return c.extract_from_text(text)


def extract_from_document(
    path_or_uri: str,
    project: Optional[str] = None,
    bucket: Optional[str] = None,
    mime_type: str = "application/pdf",
) -> dict[str, Any]:
    """One-off: extract structured data from a document."""
    c = EHRConverter(project=project, bucket=bucket)
    return c.extract_from_document(path_or_uri, mime_type=mime_type)
