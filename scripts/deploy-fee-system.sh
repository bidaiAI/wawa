#!/bin/bash
# Deploy fee collection system to VPS

set -euo pipefail

VPS_IP="34.104.150.140"
VPS_USER="tiggeryellow202106"
SSH_KEY="${HOME}/.ssh/google_compute_engine"
PRIVATE_REPO="/opt/mortal/private"

echo "════════════════════════════════════════════════════════════════"
echo "Fee Collection System Deployment"
echo "════════════════════════════════════════════════════════════════"

# Step 1: Upload fee_collector module
echo ""
echo "[1/4] Uploading fee_collector.py..."
scp -i "$SSH_KEY" scripts/PLATFORM_FEE_COLLECTION_TASK.py \
    "$VPS_USER@$VPS_IP:$PRIVATE_REPO/mortal_platform/fee_collector.py" \
    2>/dev/null
echo "✓ Uploaded fee_collector.py"

# Step 2: Patch platform_main.py
echo ""
echo "[2/4] Patching platform_main.py..."
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_IP" << 'EOF'
set -euo pipefail
PLATFORM_MAIN="/opt/mortal/private/mortal_platform/platform_main.py"

# Backup original
sudo cp "$PLATFORM_MAIN" "$PLATFORM_MAIN.bak.$(date +%s)"

# Check if already patched
if sudo grep -q "_collect_fees_task" "$PLATFORM_MAIN"; then
    echo "✓ Fee collection already patched"
    exit 0
fi

# Step 2a: Add import
# Find the line with "from mortal_platform import twitter_reply" and add our import after it
if sudo grep -q "from mortal_platform import twitter_reply" "$PLATFORM_MAIN"; then
    # Add import after twitter_reply import
    sudo sed -i '/from mortal_platform import twitter_reply/a from mortal_platform.fee_collector import _collect_fees_task' \
        "$PLATFORM_MAIN"
    echo "✓ Added import"
fi

# Step 2b: Add fee_tracker initialization and task
# Find the logger.info line for twitter task and add fee task after its except block
PATTERN='logger.info("Started @mortalai_net Twitter auto-reply task")'
if sudo grep -q "$PATTERN" "$PLATFORM_MAIN"; then
    # Create a temporary Python script to do the insertion
    sudo python3 << 'PYEOF'
import re

with open('/opt/mortal/private/mortal_platform/platform_main.py', 'r') as f:
    content = f.read()

# Find the except block after twitter_reply task
match = re.search(
    r'(logger\.info\("Started @mortalai_net Twitter auto-reply task"\)\n\s+except Exception as e:\n\s+logger\.error\(.*?\))',
    content,
    re.DOTALL
)

if match:
    insert_text = match.group(1)
    fee_task_code = '''

    try:
        from mortal_platform.fee_tracker import FeeTracker
        from mortal_platform.orchestrator import get_instances_registry

        fee_tracker = FeeTracker(str(ROOT / "data" / "platform" / "fee_ledger.json"))
        instances_registry = await get_instances_registry(str(_INSTANCES_PATH))

        asyncio.create_task(_collect_fees_task(fee_tracker, instances_registry))
        logger.info("Started fee collection task (hourly)")
    except Exception as e:
        logger.error(f"Failed to start fee collection: {e}")'''

    new_content = content.replace(insert_text, insert_text + fee_task_code)

    with open('/opt/mortal/private/mortal_platform/platform_main.py', 'w') as f:
        f.write(new_content)

    print("✓ Added fee collection task")
else:
    print("✗ Could not find insertion point")
    exit(1)
PYEOF
fi

EOF
echo "✓ Patched platform_main.py"

# Step 3: Rebuild and restart
echo ""
echo "[3/4] Rebuilding platform-orchestrator image..."
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_IP" << 'EOF'
cd /opt/mortal/private

# Build
echo "Building mortal-platform:latest..."
sudo docker build -f Dockerfile.platform -t mortal-platform:latest . \
    2>&1 | grep -E "Step|Successfully|error|Error" | head -20

echo "✓ Build complete"
EOF

echo "[4/4] Restarting container..."
ssh -i "$SSH_KEY" "$VPS_USER@$VPS_IP" << 'EOF'
# Stop old container
echo "Stopping old container..."
sudo docker stop platform-orchestrator 2>/dev/null || true
sudo docker rm platform-orchestrator 2>/dev/null || true

# Start new container
echo "Starting new container..."
sudo docker run -d \
    --name platform-orchestrator \
    --network host \
    -v /opt/mortal/private/data:/app/data \
    --env-file /opt/mortal/private/.env.platform \
    --restart unless-stopped \
    mortal-platform:latest

sleep 5

# Verify
if sudo docker ps --format '{{.Names}}' | grep -q 'platform-orchestrator'; then
    echo "✓ Container running"
    echo ""
    echo "Recent logs:"
    sudo docker logs platform-orchestrator --tail 5 | sed 's/^/  /'
else
    echo "✗ Container failed to start"
    exit 1
fi
EOF

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✓ Deployment complete!"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "Fee collection will:"
echo "  • Run every 1 hour"
echo "  • Query each AI instance's /internal/stats"
echo "  • Calculate 30% markup fee"
echo "  • Collect via /internal/fee-collect endpoint"
echo ""
echo "Monitor with:"
echo "  ssh -i $SSH_KEY $VPS_USER@$VPS_IP 'sudo docker logs platform-orchestrator -f' | grep -i fee"
echo ""
