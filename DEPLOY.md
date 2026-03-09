# Deploy to Vercel (always-on site + EHR API)

Deploy this repo to Vercel so the whole site (hub, sign-in, MARCo, EHR Conversion) and the **EHR Extract from text** API are always available—no local server.

## Steps

1. **Push to GitHub** (if not already) and **import the repo** in [Vercel](https://vercel.com).
2. **Create a GCP service account key** (so Vercel can call Vertex AI):
   - In [Google Cloud Console](https://console.cloud.google.com/), go to **IAM & Admin → Service Accounts** (project `penfield-ai-dev`).
   - Create a service account (or use an existing one), grant **Vertex AI User** (and **Storage Object Creator** for PDF).
   - Create a **JSON key** and download the file.

3. **Set environment variables** in Vercel (**Project → Settings → Environment Variables**):

   | Key | Value |
   |-----|--------|
   | `GOOGLE_APPLICATION_CREDENTIALS_JSON` | **Paste the entire contents** of the JSON key file. |
   | `GOOGLE_CLOUD_PROJECT` | `penfield-ai-dev` (optional; default) |
   | `GOOGLE_CLOUD_BUCKET` | `penfield-dev` (optional; default) |

   Without `GOOGLE_APPLICATION_CREDENTIALS_JSON` you get *"Your default credentials were not found"*.

4. **Deploy.** Vercel will serve static files and run **`/api/extract-text`** and **`/api/extract-document`** (PDF).

After deploy, the EHR Conversion page’s “Extract from text” has **Extract from text** and **Extract from PDF**; both call the live API. No need to run `ehr_server.py` or `run_ehr.sh`.

## Local development

- **Static only:** `python3 -m http.server 8080` → site works; EHR Extract will fail (no API).
- **With EHR API:** Set `GOOGLE_APPLICATION_CREDENTIALS_JSON` (same JSON key) or run `gcloud auth application-default login`, then `./run_ehr.sh` or `python ehr_server.py` → full app at http://localhost:5000.
