"""
Platform Server — Entry Point

Runs the mortal-ai platform backend:
  - AI instance lifecycle management (Orchestrator)
  - Creator dashboard API (wallet-authenticated)
  - Admin dashboard API (admin wallet required)
  - Platform Twitter proxy for hosted AIs
  - Cost aggregation, fee tracking, encrypted key storage

Usage:
  python -m mortal_platform.platform_main
  # or via uvicorn:
  uvicorn mortal_platform.platform_main:app

Environment variables:
  PLATFORM_AUTH_SECRET       JWT signing key (required in production)
  PLATFORM_ADMIN_WALLETS     Comma-separated admin wallet addresses
  PLATFORM_FEE_SECRET        Shared secret for AI fee collection
  PLATFORM_TWEET_SECRET      Shared secret for AI tweet proxy
  PLATFORM_ALLOWED_ORIGINS   Comma-separated CORS origins
  PLATFORM_DATA_DIR          Data directory (default: data)
  PLATFORM_BASE_PORT         First port for AI containers (default: 8100)
  HOST                       Server bind host (default: 0.0.0.0)
  PORT                       Server bind port (default: 8001)
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from mortal_platform.orchestrator import Orchestrator
from mortal_platform.key_manager import KeyManager
from mortal_platform.cost_aggregator import CostAggregator, POLL_INTERVAL
from mortal_platform.fee_tracker import FeeTracker
from mortal_platform.api import create_platform_app

# ── Logging ────────────────────────────────────────────────────

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(name)s] %(levelname)s  %(message)s",
)
logger = logging.getLogger("mortal.platform.main")

# ── Config ─────────────────────────────────────────────────────

DATA_DIR = Path(os.getenv("PLATFORM_DATA_DIR", "data"))
BASE_PORT = int(os.getenv("PLATFORM_BASE_PORT", "8100"))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8001"))

# ── Background polling task ─────────────────────────────────────

async def _cost_poll_loop(orchestrator: Orchestrator, cost_aggregator: CostAggregator, fee_tracker: FeeTracker):
    """Poll all live AI instances for cost data every POLL_INTERVAL seconds."""
    logger.info(f"Cost polling started (interval: {POLL_INTERVAL}s)")
    while True:
        try:
            all_stats = await orchestrator.fetch_all_instance_stats()
            for inst in all_stats:
                subdomain = inst.get("subdomain", "")
                stats = inst.get("stats")
                if subdomain and stats:
                    cost_aggregator.record_snapshot(subdomain, stats)
                    # Update fee tracker with latest API cost
                    cost_guard = stats.get("cost_guard", {})
                    total_api_cost = cost_guard.get("total_api_cost_usd", 0)
                    if total_api_cost > 0:
                        fee_tracker.record_usage(subdomain, total_api_cost)

            # Persist periodically
            cost_aggregator.save()
            fee_tracker.save()

        except Exception as e:
            logger.warning(f"Cost poll cycle error: {e}")

        await asyncio.sleep(POLL_INTERVAL)


# ── App factory ────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Build the platform FastAPI app with all modules initialized."""

    orchestrator = Orchestrator(
        data_dir=str(DATA_DIR / "platform"),
        base_port=BASE_PORT,
    )

    key_manager = KeyManager(data_dir=DATA_DIR)
    cost_aggregator = CostAggregator(data_dir=DATA_DIR)
    fee_tracker = FeeTracker(data_dir=DATA_DIR)

    logger.info(
        f"Platform initialized — "
        f"deployments: {orchestrator.get_status()['total_deployments']}, "
        f"keys: {key_manager.get_status()['providers_configured']}"
    )

    # Propagate stored LLM keys to app context so orchestrator can use them
    # when generating .env files for new instances
    stored_keys = key_manager.get_all_keys()
    if stored_keys:
        logger.info(f"Loaded stored API keys for providers: {list(stored_keys.keys())}")

    platform_app = create_platform_app(
        orchestrator=orchestrator,
        key_manager=key_manager,
        cost_aggregator=cost_aggregator,
        fee_tracker=fee_tracker,
    )

    # Wire background polling into lifespan
    @platform_app.on_event("startup")
    async def startup():
        logger.info(f"Platform server starting on {HOST}:{PORT}")
        # Start background cost polling
        asyncio.create_task(
            _cost_poll_loop(orchestrator, cost_aggregator, fee_tracker),
            name="cost_poll",
        )

    @platform_app.on_event("shutdown")
    async def shutdown():
        logger.info("Platform server shutting down — saving state...")
        cost_aggregator.save()
        fee_tracker.save()
        orchestrator._save_state()

    return platform_app


# Module-level app for uvicorn
app = create_app()


# ── Entry point ────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "mortal_platform.platform_main:app",
        host=HOST,
        port=PORT,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        reload=os.getenv("DEV", "false").lower() in ("true", "1"),
    )
