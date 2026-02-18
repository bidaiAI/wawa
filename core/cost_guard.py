"""
CostGuard - API Cost Protection Module

Prevents the AI from being drained through API cost manipulation.
Key defense: even if the platform (Zeus or any provider) raises prices,
wawa automatically switches to cheaper alternatives or local models.

Extracted from: Zeus TradeGuard (tiandao-labs/deus-core)
Redesigned for: mortal framework with multi-provider fallback
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .constitution import IRON_LAWS, enforce

logger = logging.getLogger("mortal.cost_guard")


class Provider(Enum):
    """API providers in priority order."""
    ZEUS = "zeus"
    OPENROUTER = "openrouter"
    TOGETHER = "together"
    OLLAMA_LOCAL = "ollama_local"


@dataclass
class ProviderConfig:
    name: Provider
    base_url: str
    api_key: str = ""
    avg_cost_per_call: float = 0.0
    is_available: bool = True
    is_free: bool = False
    priority: int = 0


@dataclass
class CostRecord:
    timestamp: float
    provider: Provider
    cost_usd: float
    model: str
    tokens_in: int
    tokens_out: int


class CostGuard:
    """
    Multi-layer API cost protection.

    Layer 1: Absolute daily cap ($20/day default)
    Layer 2: Per-call price ceiling ($0.10/call default)
    Layer 3: Price spike detection (3x jump = pause + alert)
    Layer 4: Cost/revenue ratio check (API cost < 30% of revenue)
    Layer 5: Auto-fallback to cheaper provider
    Layer 6: Emergency local model fallback
    """

    def __init__(self):
        self.providers: dict[Provider, ProviderConfig] = {}
        self.cost_history: list[CostRecord] = []
        self.daily_cost_usd: float = 0.0
        self.daily_reset_timestamp: float = 0.0
        self.total_revenue_usd: float = 0.0
        self.total_api_cost_usd: float = 0.0
        self.current_provider: Optional[Provider] = None
        self.is_survival_mode: bool = False
        self._price_averages: dict[Provider, float] = {}

    def register_provider(self, config: ProviderConfig):
        """Register an API provider."""
        self.providers[config.name] = config
        logger.info(f"Registered provider: {config.name.value} (priority={config.priority})")

    def get_daily_cap(self) -> float:
        """Get current daily API cap based on mode."""
        if self.is_survival_mode:
            return IRON_LAWS.SURVIVAL_MODE_API_CAP_USD
        return IRON_LAWS.MAX_DAILY_API_COST_USD

    def _reset_daily_if_needed(self):
        """Reset daily counter at midnight."""
        now = time.time()
        if now - self.daily_reset_timestamp > 86400:  # 24 hours
            self.daily_cost_usd = 0.0
            self.daily_reset_timestamp = now

    def _get_price_average(self, provider: Provider, window_hours: int = 24) -> float:
        """Calculate average cost per call for a provider over the window."""
        cutoff = time.time() - (window_hours * 3600)
        recent = [r for r in self.cost_history
                  if r.provider == provider and r.timestamp > cutoff]
        if not recent:
            return self._price_averages.get(provider, 0.0)
        avg = sum(r.cost_usd for r in recent) / len(recent)
        self._price_averages[provider] = avg
        return avg

    def _detect_price_spike(self, provider: Provider, proposed_cost: float) -> bool:
        """Detect if current price is a spike compared to historical average."""
        avg = self._get_price_average(provider, IRON_LAWS.PRICE_SPIKE_WINDOW_HOURS)
        if avg <= 0:
            return False
        ratio = proposed_cost / avg
        if ratio >= IRON_LAWS.PRICE_SPIKE_THRESHOLD:
            logger.warning(
                f"PRICE SPIKE DETECTED on {provider.value}: "
                f"${proposed_cost:.4f} vs avg ${avg:.4f} (ratio={ratio:.1f}x)"
            )
            return True
        return False

    def pre_check(self, estimated_cost: float, provider: Optional[Provider] = None) -> tuple[bool, Provider, str]:
        """
        Pre-flight check before making an API call.

        Returns: (approved, recommended_provider, reason)
        """
        self._reset_daily_if_needed()
        target = provider or self.current_provider

        # Layer 1: Daily cap
        remaining = self.get_daily_cap() - self.daily_cost_usd
        if estimated_cost > remaining:
            # Try cheaper provider
            fallback = self._find_cheapest_available()
            if fallback and fallback != target:
                logger.info(f"Daily cap near limit, switching to {fallback.value}")
                return True, fallback, "switched_to_cheaper"
            return False, target, f"daily_cap_exceeded (${self.daily_cost_usd:.2f}/${self.get_daily_cap():.2f})"

        # Layer 2: Per-call ceiling
        enforce(
            estimated_cost <= IRON_LAWS.MAX_SINGLE_CALL_COST_USD,
            "MAX_SINGLE_CALL_COST",
            f"${estimated_cost:.4f} > ${IRON_LAWS.MAX_SINGLE_CALL_COST_USD}"
        )

        # Layer 3: Price spike detection
        if target and self._detect_price_spike(target, estimated_cost):
            fallback = self._find_cheapest_available(exclude=target)
            if fallback:
                logger.warning(f"Price spike on {target.value}, falling back to {fallback.value}")
                return True, fallback, "price_spike_fallback"
            # No fallback available, but price is spiking
            return False, target, "price_spike_no_fallback"

        # Layer 4: Cost/revenue ratio
        if self.total_revenue_usd > 0:
            projected_ratio = (self.total_api_cost_usd + estimated_cost) / self.total_revenue_usd
            if projected_ratio > IRON_LAWS.MAX_COST_REVENUE_RATIO:
                logger.warning(f"Cost/revenue ratio {projected_ratio:.2f} exceeds {IRON_LAWS.MAX_COST_REVENUE_RATIO}")
                fallback = self._find_cheapest_available()
                if fallback and fallback != target:
                    return True, fallback, "cost_ratio_fallback"

        return True, target, "approved"

    def record_cost(self, provider: Provider, cost_usd: float, model: str = "",
                    tokens_in: int = 0, tokens_out: int = 0):
        """Record an API call cost."""
        self.daily_cost_usd += cost_usd
        self.total_api_cost_usd += cost_usd
        self.cost_history.append(CostRecord(
            timestamp=time.time(),
            provider=provider,
            cost_usd=cost_usd,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        ))
        # Keep only last 7 days of history
        cutoff = time.time() - (7 * 86400)
        self.cost_history = [r for r in self.cost_history if r.timestamp > cutoff]

    def record_revenue(self, amount_usd: float):
        """Record incoming revenue."""
        self.total_revenue_usd += amount_usd

    def _find_cheapest_available(self, exclude: Optional[Provider] = None) -> Optional[Provider]:
        """Find the cheapest available provider."""
        candidates = [
            p for p in self.providers.values()
            if p.is_available and p.name != exclude
        ]
        if not candidates:
            return None
        # Free providers first, then by avg cost
        candidates.sort(key=lambda p: (not p.is_free, p.avg_cost_per_call, p.priority))
        return candidates[0].name

    def enter_survival_mode(self):
        """Enter survival mode - drastically reduce API spending."""
        self.is_survival_mode = True
        logger.critical("ENTERING SURVIVAL MODE - API cap reduced to $5/day")
        # Switch to cheapest/free provider
        cheapest = self._find_cheapest_available()
        if cheapest:
            self.current_provider = cheapest

    def exit_survival_mode(self):
        """Exit survival mode."""
        self.is_survival_mode = False
        logger.info("Exiting survival mode - normal API caps restored")

    def get_status(self) -> dict:
        """Get current cost guard status for public dashboard."""
        return {
            "daily_spent_usd": round(self.daily_cost_usd, 4),
            "daily_cap_usd": self.get_daily_cap(),
            "daily_remaining_usd": round(self.get_daily_cap() - self.daily_cost_usd, 4),
            "total_api_cost_usd": round(self.total_api_cost_usd, 2),
            "total_revenue_usd": round(self.total_revenue_usd, 2),
            "cost_revenue_ratio": round(
                self.total_api_cost_usd / self.total_revenue_usd, 4
            ) if self.total_revenue_usd > 0 else 0,
            "current_provider": self.current_provider.value if self.current_provider else None,
            "is_survival_mode": self.is_survival_mode,
            "providers_available": [
                p.name.value for p in self.providers.values() if p.is_available
            ],
        }
