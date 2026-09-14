#!/usr/bin/env bash
# Läuft alle 2 Minuten per systemd-Timer auf dem Server (siehe install-auto-deploy.sh).
# Prüft, ob origin/main neuer ist als der laufende Stand. Wenn ja und die GitHub-Tests
# ("verify") für diesen Commit grün sind, wird scripts/deploy-server.sh ausgeführt.
# Braucht keine Zugangsdaten: Repository und Check-Status sind öffentlich lesbar.
{
  set -euo pipefail

  APP_DIR="${APP_DIR:-/opt/automatic-clips}"
  BRANCH="${BRANCH:-main}"
  REPO="${REPO:-johannesjwolf-coder/automatic-clips}"
  CHECK_NAME="${CHECK_NAME:-verify}"        # Job-Name in .github/workflows/verify.yml
  REQUIRE_CHECKS="${REQUIRE_CHECKS:-1}"     # 0 = ohne Test-Prüfung sofort deployen
  STATE_DIR=/var/lib/clipcontrol-autodeploy
  mkdir -p "$STATE_DIR"

  cd "$APP_DIR"
  git fetch -q --prune origin "$BRANCH"
  local_sha=$(git rev-parse HEAD)
  remote_sha=$(git rev-parse "origin/$BRANCH")

  if [ "$local_sha" = "$remote_sha" ]; then
    exit 0
  fi

  # Einen bereits als fehlgeschlagen erkannten Commit nicht ständig neu abfragen.
  if [ -f "$STATE_DIR/failed" ] && [ "$(cat "$STATE_DIR/failed")" = "$remote_sha" ]; then
    exit 0
  fi

  if [ "$REQUIRE_CHECKS" = "1" ]; then
    conclusion=$(curl -fsS -H "Accept: application/vnd.github+json" \
      "https://api.github.com/repos/$REPO/commits/$remote_sha/check-runs" \
      | CHECK_NAME="$CHECK_NAME" python3 -c '
import json, sys, os
name = os.environ["CHECK_NAME"]
runs = [r for r in json.load(sys.stdin).get("check_runs", []) if r.get("name") == name]
if not runs:
    print("none")
else:
    r = max(runs, key=lambda r: r.get("started_at") or "")
    print(r.get("conclusion") or r.get("status") or "unknown")
') || conclusion="api-error"

    case "$conclusion" in
      success)
        echo "Commit ${remote_sha:0:7}: Tests grün – starte Deployment."
        ;;
      none|queued|in_progress|pending)
        echo "Commit ${remote_sha:0:7}: Tests laufen noch ($conclusion) – warte."
        exit 0
        ;;
      failure|cancelled|timed_out|action_required)
        echo "Commit ${remote_sha:0:7}: Tests NICHT bestanden ($conclusion) – kein Deployment."
        echo "$remote_sha" > "$STATE_DIR/failed"
        exit 0
        ;;
      *)
        echo "Commit ${remote_sha:0:7}: Status unbekannt ($conclusion) – versuche es später erneut."
        exit 0
        ;;
    esac
  else
    echo "Commit ${remote_sha:0:7}: neuer Stand – starte Deployment (ohne Test-Prüfung)."
  fi

  exec "$APP_DIR/scripts/deploy-server.sh"
}
