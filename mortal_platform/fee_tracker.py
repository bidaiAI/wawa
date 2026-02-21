"""
Fee Tracker — Tracks API usage fees owed by each AI to the platform.

Platform charges AIs a markup on API costs. The markup covers:
key management, infrastructure, monitoring.

Formula: fee_owed = total_api_cost * markup_rate
"""

import json
import time
import logging
from pathlib import Path

logger = logging.getLogger("mortal.platform.fee_tracker")


class FeeTracker:
    """Tracks per-AI API usage fees."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.config_file = data_dir / "platform" / "fee_config.json"
        self.ledger_file = data_dir / "platform" / "fee_ledger.json"
        self._config = {
            "markup_rate": 0.30,  # 30% markup on API costs
            "collection_wallet": "",
            "min_collection_threshold": 5.0,  # Don't collect below $5
        }
        self._ledger: dict[str, dict] = {}  # subdomain -> fee data
        self._collection_log: list[dict] = []  # history of collections
        self._load()

    def _load(self):
        """Load config and ledger from disk."""
        if self.config_file.exists():
            try:
                self._config.update(
                    json.loads(self.config_file.read_text(encoding="utf-8"))
                )
            except Exception as e:
                logger.warning(f"Failed to load fee config: {e}")

        if self.ledger_file.exists():
            try:
                data = json.loads(self.ledger_file.read_text(encoding="utf-8"))
                self._ledger = data.get("ledger", {})
                self._collection_log = data.get("collections", [])
                logger.info(f"Loaded fee data for {len(self._ledger)} AIs")
            except Exception as e:
                logger.warning(f"Failed to load fee ledger: {e}")

    def _save(self):
        """Persist config and ledger to disk."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self._config, indent=2), encoding="utf-8"
        )
        self.ledger_file.write_text(
            json.dumps({
                "ledger": self._ledger,
                "collections": self._collection_log[-1000:],  # Keep last 1000
            }, indent=2),
            encoding="utf-8",
        )

    def update_config(self, markup_rate: float = None,
                      collection_wallet: str = None,
                      min_collection_threshold: float = None):
        """Update fee configuration."""
        if markup_rate is not None:
            self._config["markup_rate"] = max(0, min(markup_rate, 1.0))
        if collection_wallet is not None:
            self._config["collection_wallet"] = collection_wallet
        if min_collection_threshold is not None:
            self._config["min_collection_threshold"] = max(0, min_collection_threshold)
        self._save()
        logger.info(f"Fee config updated: {self._config}")

    def record_usage(self, subdomain: str, total_api_cost: float):
        """Update total API cost for an AI (called from cost polling)."""
        if subdomain not in self._ledger:
            self._ledger[subdomain] = {
                "total_api_cost_usd": 0.0,
                "total_fees_owed_usd": 0.0,
                "total_fees_collected_usd": 0.0,
                "last_updated": 0,
            }

        entry = self._ledger[subdomain]
        entry["total_api_cost_usd"] = total_api_cost
        entry["total_fees_owed_usd"] = round(
            total_api_cost * self._config["markup_rate"], 4
        )
        entry["last_updated"] = time.time()

    def record_collection(self, subdomain: str, amount: float):
        """Record a successful fee collection."""
        if subdomain not in self._ledger:
            return
        entry = self._ledger[subdomain]
        entry["total_fees_collected_usd"] = round(
            entry.get("total_fees_collected_usd", 0) + amount, 4
        )
        self._collection_log.append({
            "timestamp": time.time(),
            "subdomain": subdomain,
            "amount_usd": amount,
        })
        self._save()
        logger.info(f"Fee collected from {subdomain}: ${amount:.4f}")

    def get_outstanding(self, subdomain: str) -> float:
        """Get outstanding (uncollected) fees for an AI."""
        entry = self._ledger.get(subdomain, {})
        owed = entry.get("total_fees_owed_usd", 0)
        collected = entry.get("total_fees_collected_usd", 0)
        return round(max(0, owed - collected), 4)

    def get_fees_summary(self) -> dict:
        """Get full fee summary for admin dashboard."""
        per_ai = []
        total_owed = 0.0
        total_collected = 0.0
        for subdomain, entry in self._ledger.items():
            owed = entry.get("total_fees_owed_usd", 0)
            collected = entry.get("total_fees_collected_usd", 0)
            outstanding = max(0, owed - collected)
            total_owed += owed
            total_collected += collected
            per_ai.append({
                "subdomain": subdomain,
                "total_api_cost_usd": round(entry.get("total_api_cost_usd", 0), 4),
                "fees_owed_usd": round(owed, 4),
                "fees_collected_usd": round(collected, 4),
                "outstanding_usd": round(outstanding, 4),
                "last_updated": entry.get("last_updated", 0),
            })
        return {
            "config": self._config,
            "totals": {
                "total_fees_owed_usd": round(total_owed, 4),
                "total_fees_collected_usd": round(total_collected, 4),
                "total_outstanding_usd": round(max(0, total_owed - total_collected), 4),
            },
            "per_ai": sorted(per_ai, key=lambda x: x["outstanding_usd"], reverse=True),
        }

    def get_collection_log(self, limit: int = 50) -> list[dict]:
        """Get recent fee collections."""
        return self._collection_log[-limit:]

    def save(self):
        """Persist to disk."""
        self._save()

    def get_status(self) -> dict:
        return {
            "ais_tracked": len(self._ledger),
            "markup_rate": self._config["markup_rate"],
            "collection_wallet": self._config["collection_wallet"],
        }
