#!/usr/bin/env bash
# Wird auf dem Hetzner-Server ausgeführt (per GitHub Actions über SSH oder manuell).
# Holt den neuesten Stand von main und baut ClipControl neu.
#
# Der gesamte Ablauf steht in einem { ... } Block: Bash liest den Block vollständig ein,
# bevor er ausgeführt wird. So ist es unproblematisch, dass "git reset" diese Datei
# währenddessen selbst aktualisiert.
{
  set -euo pipefail

  APP_DIR="${APP_DIR:-/opt/automatic-clips}"
  BRANCH="${BRANCH:-main}"
  LOCK="/tmp/clipcontrol-deploy.lock"

  cd "$APP_DIR"

  # Nur ein Deploy gleichzeitig.
  exec 9>"$LOCK"
  if ! flock -n 9; then
    echo "Ein anderes Deployment läuft bereits – Abbruch."
    exit 1
  fi

  echo "==> Aktueller Stand: $(git rev-parse --short HEAD)"
  git fetch --prune origin "$BRANCH"
  git reset --hard "origin/$BRANCH"
  echo "==> Neuer Stand:     $(git rev-parse --short HEAD) – $(git log -1 --pretty=%s)"

  echo "==> Baue und starte Container"
  docker compose up -d --build --remove-orphans

  echo "==> Warte auf Healthcheck"
  for i in $(seq 1 30); do
    if curl -fsS -o /dev/null http://127.0.0.1:8000/; then
      echo "==> ClipControl antwortet. Deployment fertig."
      docker image prune -f >/dev/null
      exit 0
    fi
    sleep 2
  done

  echo "!! ClipControl antwortet nach 60 s nicht. Container-Status:"
  docker compose ps
  docker compose logs --tail=50
  exit 1
}
