#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend install --no-audit --no-fund
npm --prefix frontend run build
mkdir -p data
