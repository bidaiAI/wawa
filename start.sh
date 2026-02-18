#!/bin/sh
# wawa - Production startup script (Railway)
# Runs validation then starts uvicorn

set -e

echo "=== wawa startup ==="
echo "Time: $(date -u)"

# Step 1: Import validation
echo "[1/3] Validating imports..."
python -c "
import fastapi, uvicorn, openai, httpx
from core.constitution import IRON_LAWS, WAWA_IDENTITY
from core.vault import VaultManager
from core.cost_guard import CostGuard
from core.chat_router import ChatRouter
from api.server import create_app
print('All imports OK')
"

# Step 2: Ensure data directories exist
echo "[2/3] Ensuring data directories..."
mkdir -p data/memory data/tweets data/orders

# Step 3: Start uvicorn (PID 1)
echo "[3/3] Starting wawa on port ${PORT:-8000}..."
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --log-level "${LOG_LEVEL:-info}" \
    --no-access-log
