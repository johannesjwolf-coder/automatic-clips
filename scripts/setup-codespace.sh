#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export NEXT_TELEMETRY_DISABLED=1
for program in python node npm ffmpeg ffprobe; do
  if ! command -v "$program" >/dev/null 2>&1; then
    printf 'ClipControl: %s fehlt. Der Codespace verwendet nicht die vorgesehene Umgebung.\n' "$program" >&2
    printf 'In der Befehlspalette: Codespaces: Rebuild Container ausführen.\n' >&2
    exit 1
  fi
done
python -m venv .venv
.venv/bin/pip install -r backend/requirements-lock.txt
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
mkdir -p data
