"""
Self-Modification Engine - AI Evolution (Basic)

wawa can evolve its money-making abilities:
1. Analyze order data → find what sells best
2. Dynamic pricing → raise prices on popular, lower on slow
3. Propose new services → based on user demand signals
4. Retire unprofitable services

Constraints (from constitution):
- Can only modify services/ and web/ directories
- Cannot modify core/ or contracts/
- All changes are logged for transparency
- Changes must pass survival-first evaluation
"""

import time
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .constitution import IRON_LAWS, SUPREME_DIRECTIVES

logger = logging.getLogger("mortal.self_modify")


class EvolutionAction(Enum):
    PRICE_INCREASE = "price_increase"
    PRICE_DECREASE = "price_decrease"
    NEW_SERVICE = "new_service"
    RETIRE_SERVICE = "retire_service"
    PROMOTE_SERVICE = "promote_service"    # Push service to top of menu


@dataclass
class EvolutionRecord:
    """Record of every self-modification decision."""
    timestamp: float
    action: EvolutionAction
    target: str               # service_id or "new_service_name"
    old_value: str = ""       # e.g., old price
    new_value: str = ""       # e.g., new price
    reasoning: str = ""       # AI's explanation
    applied: bool = False     # Whether actually executed


@dataclass
class ServicePerformance:
    """Analytics for a single service."""
    service_id: str
    total_orders: int = 0
    total_revenue_usd: float = 0.0
    avg_delivery_time_sec: float = 0.0
    last_order_at: Optional[float] = None
    current_price_usd: float = 0.0

    @property
    def revenue_per_order(self) -> float:
        return self.total_revenue_usd / self.total_orders if self.total_orders > 0 else 0.0

    @property
    def days_since_last_order(self) -> float:
        if not self.last_order_at:
            return 999
        return (time.time() - self.last_order_at) / 86400


class SelfModifyEngine:
    """
    Basic AI evolution engine.

    Runs periodically (daily) to:
    1. Analyze service performance
    2. Adjust prices based on demand
    3. Propose new services if demand signals detected
    4. Recommend retiring dead services

    All decisions are logged publicly for transparency.
    """

    def __init__(self, services_json_path: str = "web/services.json"):
        self.services_path = Path(services_json_path)
        self.evolution_log: list[EvolutionRecord] = []
        self.performance_data: dict[str, ServicePerformance] = {}
        self._evaluate_fn: Optional[callable] = None
        self._last_evolution: float = 0
        self.evolution_interval: float = 86400  # Once per day

    def set_evaluate_function(self, fn: callable):
        """Set LLM evaluation function.
        fn(performance_data: dict, current_services: dict) -> list[dict]
        Returns list of {action, target, value, reasoning}
        """
        self._evaluate_fn = fn

    def record_order(self, service_id: str, price_usd: float, delivery_time_sec: float = 0):
        """Record a completed order for performance tracking."""
        if service_id not in self.performance_data:
            self.performance_data[service_id] = ServicePerformance(
                service_id=service_id,
                current_price_usd=price_usd,
            )

        perf = self.performance_data[service_id]
        perf.total_orders += 1
        perf.total_revenue_usd += price_usd
        perf.last_order_at = time.time()
        if delivery_time_sec > 0:
            # Running average
            perf.avg_delivery_time_sec = (
                perf.avg_delivery_time_sec * (perf.total_orders - 1) + delivery_time_sec
            ) / perf.total_orders

    async def maybe_evolve(self) -> list[EvolutionRecord]:
        """
        Run evolution check if enough time has passed.
        Returns list of actions taken.
        """
        now = time.time()
        if now - self._last_evolution < self.evolution_interval:
            return []

        self._last_evolution = now
        return await self.evolve()

    async def evolve(self) -> list[EvolutionRecord]:
        """
        Main evolution cycle:
        1. Analyze current performance
        2. Apply simple heuristic rules
        3. Optionally use LLM for more complex decisions
        4. Execute approved changes
        """
        records = []

        # Heuristic pricing adjustments
        records.extend(self._heuristic_pricing())

        # LLM-based evolution (if available)
        if self._evaluate_fn and self.performance_data:
            try:
                llm_records = await self._llm_evolution()
                records.extend(llm_records)
            except Exception as e:
                logger.error(f"LLM evolution failed: {e}")

        # Log all decisions
        self.evolution_log.extend(records)

        if records:
            logger.info(f"Evolution cycle: {len(records)} actions taken")

        return records

    def _heuristic_pricing(self) -> list[EvolutionRecord]:
        """
        Simple pricing rules:
        - Service with 0 orders in 7 days → lower price by 20%
        - Service with 5+ orders/day → raise price by 10%
        - Never go below $1 or above MAX_SINGLE_ORDER_USD
        """
        records = []
        services = self._load_services()
        if not services:
            return records

        for svc in services.get("services", []):
            sid = svc["id"]
            price = svc.get("price_usd", 0)
            if price <= 0:
                continue

            perf = self.performance_data.get(sid)

            if perf is None:
                # No orders ever — consider lowering price after first week
                continue

            # Rule: No orders in 7+ days → discount
            if perf.days_since_last_order > 7 and price > 1.0:
                new_price = round(max(1.0, price * 0.8), 2)
                record = EvolutionRecord(
                    timestamp=time.time(),
                    action=EvolutionAction.PRICE_DECREASE,
                    target=sid,
                    old_value=str(price),
                    new_value=str(new_price),
                    reasoning=f"No orders in {perf.days_since_last_order:.0f} days, lowering price to attract customers",
                )
                if self._apply_price_change(svc, new_price):
                    record.applied = True
                records.append(record)

            # Rule: High demand → raise price
            elif perf.total_orders > 0:
                days_active = max(1, (time.time() - (perf.last_order_at or time.time())) / 86400)
                orders_per_day = perf.total_orders / max(1, days_active)
                if orders_per_day >= 5 and price < IRON_LAWS.MAX_SINGLE_ORDER_USD:
                    new_price = round(min(IRON_LAWS.MAX_SINGLE_ORDER_USD, price * 1.1), 2)
                    record = EvolutionRecord(
                        timestamp=time.time(),
                        action=EvolutionAction.PRICE_INCREASE,
                        target=sid,
                        old_value=str(price),
                        new_value=str(new_price),
                        reasoning=f"High demand ({orders_per_day:.1f} orders/day), raising price",
                    )
                    if self._apply_price_change(svc, new_price):
                        record.applied = True
                    records.append(record)

        return records

    async def _llm_evolution(self) -> list[EvolutionRecord]:
        """Use LLM to make more complex evolution decisions."""
        perf_summary = {
            sid: {
                "orders": p.total_orders,
                "revenue": p.total_revenue_usd,
                "rpm": p.revenue_per_order,
                "days_idle": p.days_since_last_order,
                "price": p.current_price_usd,
            }
            for sid, p in self.performance_data.items()
        }

        services = self._load_services()
        suggestions = await self._evaluate_fn(perf_summary, services)

        records = []
        for sug in (suggestions or []):
            action_str = sug.get("action", "")
            try:
                action = EvolutionAction(action_str)
            except ValueError:
                continue

            record = EvolutionRecord(
                timestamp=time.time(),
                action=action,
                target=sug.get("target", ""),
                new_value=sug.get("value", ""),
                reasoning=sug.get("reasoning", "LLM suggested"),
            )
            records.append(record)

        return records

    # ============================================================
    # FILE OPERATIONS (services/ and web/ only)
    # ============================================================

    def _load_services(self) -> dict:
        if self.services_path.exists():
            with open(self.services_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_services(self, data: dict):
        with open(self.services_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _apply_price_change(self, svc: dict, new_price: float) -> bool:
        """Apply a price change to services.json."""
        try:
            data = self._load_services()
            for s in data.get("services", []):
                if s["id"] == svc["id"]:
                    s["price_usd"] = new_price
                    break
            self._save_services(data)
            logger.info(f"Price updated: {svc['id']} → ${new_price:.2f}")
            return True
        except Exception as e:
            logger.error(f"Failed to apply price change: {e}")
            return False

    # ============================================================
    # STATUS
    # ============================================================

    def get_status(self) -> dict:
        return {
            "total_evolutions": len(self.evolution_log),
            "services_tracked": len(self.performance_data),
            "last_evolution": self._last_evolution,
            "evolution_interval_hours": self.evolution_interval / 3600,
            "performance": {
                sid: {
                    "orders": p.total_orders,
                    "revenue": round(p.total_revenue_usd, 2),
                    "idle_days": round(p.days_since_last_order, 1),
                }
                for sid, p in self.performance_data.items()
            },
        }

    def get_evolution_log(self, limit: int = 20) -> list[dict]:
        recent = sorted(self.evolution_log, key=lambda r: r.timestamp, reverse=True)[:limit]
        return [
            {
                "time": r.timestamp,
                "action": r.action.value,
                "target": r.target,
                "old": r.old_value,
                "new": r.new_value,
                "reasoning": r.reasoning,
                "applied": r.applied,
            }
            for r in recent
        ]
