#!/usr/bin/env bash
set -euo pipefail
python -m venv .venv
.venv/bin/pip install -r backend/requirements-lock.txt
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
mkdir -p data
