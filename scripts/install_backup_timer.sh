#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
RUN_USER="${SUDO_USER:-$(id -un)}"
SERVICE=/etc/systemd/system/task-tracker-backup.service
TIMER=/etc/systemd/system/task-tracker-backup.timer

cat > /tmp/task-tracker-backup.service <<EOF
[Unit]
Description=Task Tracker portable host backup
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/scripts/backup_host.sh
EOF

cat > /tmp/task-tracker-backup.timer <<'EOF'
[Unit]
Description=Daily Task Tracker backup

[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
EOF

sudo install -m 0644 /tmp/task-tracker-backup.service "$SERVICE"
sudo install -m 0644 /tmp/task-tracker-backup.timer "$TIMER"
rm -f /tmp/task-tracker-backup.service /tmp/task-tracker-backup.timer
sudo systemctl daemon-reload
sudo systemctl enable --now task-tracker-backup.timer
sudo systemctl list-timers task-tracker-backup.timer --no-pager

echo "Daily backup timer installed."
echo "Manual run: sudo systemctl start task-tracker-backup.service"
