# Deploy to Vercel (always-on site + EHR API)

Deploy this repo to Vercel so the whole site (hub, sign-in, MARCo, EHR Conversion) and the **EHR Extract from text** API are always available—no local server.

## Steps

1. **Push to GitHub** (if not already) and **import the repo** in [Vercel](https://vercel.com).
2. **Set environment variables** in Vercel:
   - **Project → Settings → Environment Variables**
   - Add:
     - `GOOGLE_CLOUD_PROJECT` = `penfield-ai-dev` (or your GCP project)
     - `GOOGLE_CLOUD_BUCKET` = `penfield-dev` (or your GCS bucket; used for PDF/document extraction)
   - Both default to these values in code, so you can omit them if you use penfield-ai-dev and penfield-dev.
3. **Deploy.** Vercel will:
   - Serve all static files (HTML, CSS, JS) from the root.
   - Run **`/api/extract-text`** as a serverless function (Python) on each request.

After deploy, the EHR Conversion page’s “Extract from text” button will call the live API; no need to run `ehr_server.py` or `run_ehr.sh`.

## Local development

- **Static only:** `python3 -m http.server 8080` → site works; EHR Extract will fail (no API).
- **With EHR API:** `./run_ehr.sh` or `python ehr_server.py` → full app at http://localhost:5000.
