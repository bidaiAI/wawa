"""
Cost Aggregator — Polls AI instances for cost data and aggregates.

Background task polls each live AI's /internal/stats endpoint every 60 seconds.
Stores time-series cost data for dashboard visualization.
"""

import json
import time
import logging
import asyncio
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("mortal.platform.cost_aggregator")

POLL_INTERVAL = 60  # seconds


@dataclass
class CostSnapshot:
    """Single point-in-time cost reading from an AI instance."""
    timestamp: float
    subdomain: str
    daily_spent_usd: float = 0.0
    total_api_cost_usd: float = 0.0
    total_revenue_usd: float = 0.0
    current_provider: str = ""
    current_tier: int = 0
    current_model: str = ""
    balance_usd: float = 0.0


class CostAggregator:
    """Aggregates cost data across all AI instances."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.history_file = data_dir / "platform" / "cost_history.json"
        self._history: list[dict] = []
        self._current: dict[str, CostSnapshot] = {}  # subdomain -> latest
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._load_history()

    def _load_history(self):
        """Load historical cost data from disk."""
        if self.history_file.exists():
            try:
                self._history = json.loads(
                    self.history_file.read_text(encoding="utf-8")
                )
                logger.info(f"Loaded {len(self._history)} cost history entries")
            except Exception as e:
                logger.warning(f"Failed to load cost history: {e}")
                self._history = []

    def _save_history(self):
        """Save cost history to disk (keep last 30 days)."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        # Prune entries older than 30 days
        cutoff = time.time() - 30 * 86400
        self._history = [h for h in self._history if h.get("timestamp", 0) > cutoff]
        self.history_file.write_text(
            json.dumps(self._history[-10000:], indent=None),  # Cap at 10k entries
            encoding="utf-8",
        )

    def record_snapshot(self, subdomain: str, stats: dict):
        """Record a cost snapshot from an AI instance's /internal/stats."""
        cost_guard = stats.get("cost_guard", {})
        vault = stats.get("vault", {})
        snapshot = CostSnapshot(
            timestamp=time.time(),
            subdomain=subdomain,
            daily_spent_usd=cost_guard.get("daily_spent_usd", 0),
            total_api_cost_usd=cost_guard.get("total_api_cost_usd", 0),
            total_revenue_usd=cost_guard.get("total_revenue_usd", 0),
            current_provider=cost_guard.get("current_provider", ""),
            current_tier=cost_guard.get("current_tier", 0),
            current_model=cost_guard.get("current_model", ""),
            balance_usd=vault.get("balance_usd", 0),
        )
        self._current[subdomain] = snapshot

        # Append to history (one entry per snapshot)
        self._history.append({
            "timestamp": snapshot.timestamp,
            "subdomain": subdomain,
            "daily_spent_usd": snapshot.daily_spent_usd,
            "total_api_cost_usd": snapshot.total_api_cost_usd,
            "total_revenue_usd": snapshot.total_revenue_usd,
            "provider": snapshot.current_provider,
            "tier": snapshot.current_tier,
        })

    def get_current_costs(self) -> dict:
        """Get current cost summary across all AIs."""
        by_provider: dict[str, float] = {}
        by_ai = []
        total_daily = 0.0
        total_api = 0.0
        total_revenue = 0.0

        for subdomain, snap in self._current.items():
            total_daily += snap.daily_spent_usd
            total_api += snap.total_api_cost_usd
            total_revenue += snap.total_revenue_usd
            if snap.current_provider:
                by_provider[snap.current_provider] = (
                    by_provider.get(snap.current_provider, 0) + snap.daily_spent_usd
                )
            by_ai.append({
                "subdomain": subdomain,
                "daily_spent_usd": round(snap.daily_spent_usd, 6),
                "total_api_cost_usd": round(snap.total_api_cost_usd, 4),
                "total_revenue_usd": round(snap.total_revenue_usd, 4),
                "current_provider": snap.current_provider,
                "current_tier": snap.current_tier,
                "current_model": snap.current_model,
                "balance_usd": round(snap.balance_usd, 2),
            })

        return {
            "totals": {
                "daily_spent_usd": round(total_daily, 4),
                "total_api_cost_usd": round(total_api, 4),
                "total_revenue_usd": round(total_revenue, 4),
                "instances_reporting": len(self._current),
            },
            "by_provider": {
                k: round(v, 6) for k, v in by_provider.items()
            },
            "by_ai": sorted(by_ai, key=lambda x: x["daily_spent_usd"], reverse=True),
        }

    def get_history(self, days: int = 7) -> list[dict]:
        """Get historical cost data for chart display."""
        cutoff = time.time() - days * 86400
        return [h for h in self._history if h.get("timestamp", 0) > cutoff]

    def save(self):
        """Persist history to disk."""
        self._save_history()

    def get_status(self) -> dict:
        return {
            "instances_tracked": len(self._current),
            "history_entries": len(self._history),
            "poll_interval_seconds": POLL_INTERVAL,
        }
