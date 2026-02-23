#!/bin/bash
# Auto-deploy: checks for new commits on origin/main every few minutes.
# If new code is found, pulls and rebuilds the wawa container.
#
# Setup (run once on VPS as root):
#   cp /opt/mortal/platform/scripts/auto-deploy.sh /opt/mortal/auto-deploy.sh
#   chmod +x /opt/mortal/auto-deploy.sh
#   crontab -e  # add: */3 * * * * /opt/mortal/auto-deploy.sh >> /var/log/mortal-deploy.log 2>&1
#
# Must run as root (for git + docker permissions).

set -euo pipefail

REPO_DIR="/opt/mortal/platform"
LOG_TAG="[auto-deploy]"
LOCK_FILE="/tmp/mortal-deploy.lock"

# Prevent overlapping runs
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0) ))
    if [ "$LOCK_AGE" -lt 600 ]; then
        exit 0  # Another deploy is running (< 10 min old)
    fi
    echo "$(date -Iseconds) $LOG_TAG Stale lock file ($LOCK_AGE s), removing"
    rm -f "$LOCK_FILE"
fi

cd "$REPO_DIR" || exit 1

# Fetch latest from origin
LOCAL_HEAD=$(git rev-parse HEAD)
git fetch origin main -q 2>/dev/null
REMOTE_HEAD=$(git rev-parse origin/main)

# No changes — exit silently
if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
    exit 0
fi

# New commits detected — deploy
echo "$(date -Iseconds) $LOG_TAG New commits detected: ${LOCAL_HEAD:0:8} -> ${REMOTE_HEAD:0:8}"
touch "$LOCK_FILE"

trap 'rm -f "$LOCK_FILE"' EXIT

# Pull
git pull origin main --ff-only 2>&1 | while read -r line; do
    echo "$(date -Iseconds) $LOG_TAG [git] $line"
done

# Force remove old container (avoids name conflict), then rebuild
echo "$(date -Iseconds) $LOG_TAG Rebuilding container..."
docker rm -f platform-wawa-1 2>/dev/null || true

docker compose up -d --build 2>&1 | while read -r line; do
    echo "$(date -Iseconds) $LOG_TAG [docker] $line"
done

# Verify
sleep 8
if docker ps --format '{{.Names}}' | grep -q 'wawa'; then
    echo "$(date -Iseconds) $LOG_TAG Deploy SUCCESS — container running"
else
    echo "$(date -Iseconds) $LOG_TAG Deploy FAILED — container not found!"
fi

echo "$(date -Iseconds) $LOG_TAG Done ($(git rev-parse --short HEAD))"
