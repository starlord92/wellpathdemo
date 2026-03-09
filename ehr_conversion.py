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
from vertexai.generative_models import GenerativeModel, Part
import vertexai.preview.generative_models as generative_models


# --- Prompts (same as chatui) ---
PII_SYSTEM_INSTRUCTION = """Given the sentence below containing personal information, extract all identifiable personal details and organize them meaningfully into a JSON format. Ensure that each piece of information is categorized appropriately based on its content. The output should reflect all discernible personal information from the input sentence. Make sure all dates are in dd-mm-yyyy format regardless of how they are entered
Output:
Return the extracted information in a JSON file

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
    "for clarity and completeness. Return all information extracted in a structured json file."
)

GENERATION_CONFIG = {
    "max_output_tokens": 8192,
    "temperature": 1,
    "top_p": 0.95,
}

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
    return "".join(r.text for r in responses)


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
        self._ensure_vertex()
        model = GenerativeModel(
            "gemini-2.0-flash-001",
            system_instruction=[PII_SYSTEM_INSTRUCTION],
        )
        responses = model.generate_content(
            [text],
            generation_config=GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            stream=True,
        )
        raw = _collect_stream(responses)
        cleaned = _clean_json_response(raw)
        return json.loads(cleaned)

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
            generation_config=GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            stream=True,
        )
        raw = _collect_stream(responses)
        cleaned = _clean_json_response(raw)
        return json.loads(cleaned)

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
            generation_config=GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS,
            stream=True,
        )
        transcription = _collect_stream(responses)

        # Then extract PII from transcription
        return self.extract_from_text(transcription)

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
            generation_config=GENERATION_CONFIG,
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
