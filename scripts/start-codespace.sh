#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -f frontend/out/index.html ]; then
  bash scripts/setup-codespace.sh
fi
mkdir -p data
nohup .venv/bin/python scripts/serve.py >> data/server.log 2>&1 < /dev/null &
