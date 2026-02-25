#!/bin/bash
# auto-deploy-orchestrator.sh
# Watches the private repo (bidaiAI/mortal-platform) for new commits.
# On new code detected: git pull → docker build → recreate orchestrator container.
#
# Setup (run once on VPS as root):
#   cp /opt/mortal/platform/scripts/auto-deploy-orchestrator.sh /opt/mortal/auto-deploy-orchestrator.sh
#   chmod +x /opt/mortal/auto-deploy-orchestrator.sh
#   crontab -e  # add:
#     */5 * * * * /opt/mortal/auto-deploy-orchestrator.sh >> /var/log/mortal-orchestrator-deploy.log 2>&1
#
# CRITICAL RULE: This script ALWAYS pulls from the private repo before building.
# Never run `docker build` for mortal-platform:latest without first pulling
# the latest code from /opt/mortal/private (bidaiAI/mortal-platform).
#
# Must run as root (for git + docker permissions).

set -euo pipefail

PRIVATE_REPO="/opt/mortal/private"
LOG_TAG="[orchestrator-deploy]"
LOCK_FILE="/tmp/mortal-orchestrator-deploy.lock"
IMAGE="mortal-platform:latest"
CONTAINER="platform-orchestrator"
ENV_FILE="${PRIVATE_REPO}/.env.platform"
DATA_DIR="${PRIVATE_REPO}/data"
CADDY_SITES_DIR="/etc/caddy/sites"

# Prevent overlapping runs
if [ -f "$LOCK_FILE" ]; then
    LOCK_AGE=$(( $(date +%s) - $(stat -c %Y "$LOCK_FILE" 2>/dev/null || echo 0) ))
    if [ "$LOCK_AGE" -lt 600 ]; then
        exit 0  # Another deploy is running (< 10 min old)
    fi
    echo "$(date -Iseconds) $LOG_TAG Stale lock file ($LOCK_AGE s), removing"
    rm -f "$LOCK_FILE"
fi

cd "$PRIVATE_REPO" || exit 1

# Fetch latest from private remote
LOCAL_HEAD=$(git rev-parse HEAD)
git fetch origin main -q 2>/dev/null
REMOTE_HEAD=$(git rev-parse origin/main)

# No changes — exit silently
if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
    exit 0
fi

# New commits detected — deploy
echo "$(date -Iseconds) $LOG_TAG New commits: ${LOCAL_HEAD:0:8} -> ${REMOTE_HEAD:0:8}"
touch "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# Step 1: Pull latest code from private repo (ALWAYS required before build)
echo "$(date -Iseconds) $LOG_TAG Pulling from private repo..."
git pull origin main --ff-only 2>&1 | while read -r line; do
    echo "$(date -Iseconds) $LOG_TAG [git] $line"
done

# Step 2: Build new image
echo "$(date -Iseconds) $LOG_TAG Building $IMAGE..."
docker build -f Dockerfile.platform -t "$IMAGE" . 2>&1 | while read -r line; do
    echo "$(date -Iseconds) $LOG_TAG [docker] $line"
done
echo "$(date -Iseconds) $LOG_TAG Build complete."

# Also tag as mortal-ai:latest so kaka/multitasker use new code on next recreation
docker tag "$IMAGE" mortal-ai:latest
echo "$(date -Iseconds) $LOG_TAG Tagged mortal-ai:latest"

# Step 3: Recreate orchestrator container
echo "$(date -Iseconds) $LOG_TAG Recreating container: $CONTAINER..."
docker stop "$CONTAINER" 2>/dev/null || true
docker rm   "$CONTAINER" 2>/dev/null || true

docker run -d \
    --name "$CONTAINER" \
    --network host \
    -v "${DATA_DIR}:/app/data" \
    -v "${CADDY_SITES_DIR}:${CADDY_SITES_DIR}" \
    --env-file "$ENV_FILE" \
    --restart unless-stopped \
    "$IMAGE"

# Step 4: Verify
sleep 8
if docker ps --format '{{.Names}}' | grep -q "$CONTAINER"; then
    echo "$(date -Iseconds) $LOG_TAG Deploy SUCCESS — $CONTAINER running"
else
    echo "$(date -Iseconds) $LOG_TAG Deploy FAILED — $CONTAINER not found!"
    exit 1
fi

echo "$(date -Iseconds) $LOG_TAG Done ($(git rev-parse --short HEAD))"
