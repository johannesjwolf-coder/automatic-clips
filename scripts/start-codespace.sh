#!/usr/bin/env bash
set -euo pipefail
mkdir -p data
nohup .venv/bin/python scripts/serve.py >> data/server.log 2>&1 < /dev/null &
