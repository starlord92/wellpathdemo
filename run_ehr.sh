#!/usr/bin/env bash
# One command to start the EHR app. Run from anywhere or from this folder.
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || true
python ehr_server.py
