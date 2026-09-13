#!/usr/bin/env bash
# Einmalig als root auf dem Server ausführen:
#   bash /opt/automatic-clips/scripts/install-auto-deploy.sh
# Richtet einen systemd-Timer ein, der alle 2 Minuten scripts/auto-deploy-check.sh startet.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/automatic-clips}"

cat > /etc/systemd/system/clipcontrol-autodeploy.service <<UNIT
[Unit]
Description=ClipControl: neuen Stand von GitHub prüfen und ggf. deployen
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/env bash $APP_DIR/scripts/auto-deploy-check.sh
UNIT

cat > /etc/systemd/system/clipcontrol-autodeploy.timer <<UNIT
[Unit]
Description=ClipControl Auto-Deploy alle 2 Minuten

[Timer]
OnBootSec=2min
OnUnitActiveSec=2min
RandomizedDelaySec=20s

[Install]
WantedBy=timers.target
UNIT

chmod +x "$APP_DIR/scripts/auto-deploy-check.sh" "$APP_DIR/scripts/deploy-server.sh"
systemctl daemon-reload
systemctl enable --now clipcontrol-autodeploy.timer

echo
echo "Auto-Deploy ist aktiv. Nützliche Befehle:"
echo "  systemctl list-timers clipcontrol-autodeploy.timer   # nächster Lauf"
echo "  journalctl -u clipcontrol-autodeploy -n 50            # Protokoll"
echo "  systemctl start clipcontrol-autodeploy.service        # jetzt sofort prüfen"
