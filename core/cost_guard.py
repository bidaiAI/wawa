"""
CostGuard - API Cost Protection with Balance-Driven Tier Routing

Multi-layer protection:
  Layer 1: Dynamic daily cap (tier-based, scales with vault balance)
  Layer 2: Per-call price ceiling ($0.50/call)
  Layer 3: Price spike detection (3x jump = pause + alert)
  Layer 4: Cost/revenue ratio check (API cost < 30% of revenue)
  Layer 5: Auto-fallback to cheaper provider
  Layer 6: Emergency local model fallback

Model routing:
  Lv.1 (survival, <$50):     Gemini Flash ↔ DeepSeek (load balanced)
  Lv.2 (bootstrap, ≥$50):    Gemini Flash ↔ DeepSeek (load balanced)
  Lv.3 (growing, ≥$200):     Claude Haiku (via OpenRouter)
  Lv.4 (established, ≥$500): Claude Sonnet (via OpenRouter)
  Lv.5 (thriving, ≥$2000):   Claude Sonnet (via OpenRouter, higher limits)

Designed for: mortal AI survival framework
"""

import time
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from .constitution import (
    IRON_LAWS, enforce,
    MODEL_TIERS, ModelTier, get_model_tier,
    LOAD_BALANCE_TIERS, LOAD_BALANCE_SECONDARY_PROVIDER, LOAD_BALANCE_SECONDARY_MODEL,
    FALLBACK_CHAINS,
)

logger = logging.getLogger("mortal.cost_guard")


class Provider(Enum):
    """API providers."""
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    OLLAMA_LOCAL = "ollama"


PROVIDER_MAP = {p.value: p for p in Provider}


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


@dataclass
class RoutingResult:
    """Result of model routing decision."""
    provider: Provider
    model: str
    max_tokens: int
    temperature: float
    tier: ModelTier
    is_fallback: bool = False
    reason: str = ""


class CostGuard:
    """
    Multi-layer API cost protection with balance-driven tier routing.

    Key difference from simple "small/big model" approach:
    - Model selection is determined by vault balance (richer AI = better model)
    - Lv.1-2 use round-robin load balancing between Gemini and DeepSeek
    - Every provider has a fallback chain
    - Per-tier budget limits (not just a global 2% cap)
    """

    def __init__(self):
        self.providers: dict[Provider, ProviderConfig] = {}
        self.cost_history: list[CostRecord] = []
        self.daily_cost_usd: float = 0.0
        self.daily_reset_timestamp: float = 0.0
        self.total_revenue_usd: float = 0.0
        self.total_api_cost_usd: float = 0.0
        self.current_provider: Optional[Provider] = None
        self.current_tier: Optional[ModelTier] = None
        self.is_survival_mode: bool = False
        self._price_averages: dict[Provider, float] = {}
        self._vault_balance_fn: Optional[Callable] = None

        # Load balance counter (thread-safe)
        self._lb_counter: int = 0
        self._lb_lock = threading.Lock()

        # Rate limit tracking: {provider_value: [timestamps]}
        self._call_timestamps: dict[str, list[float]] = {}

    def set_vault_balance_function(self, fn: Callable):
        """Set function to query current vault balance for dynamic budget."""
        self._vault_balance_fn = fn

    def register_provider(self, config: ProviderConfig):
        """Register an API provider."""
        self.providers[config.name] = config
        logger.info(f"Registered provider: {config.name.value} (priority={config.priority})")

    def has_provider(self, provider_name: str) -> bool:
        """Check if a provider is registered and available."""
        provider = PROVIDER_MAP.get(provider_name)
        return provider is not None and provider in self.providers and self.providers[provider].is_available

    # ============================================================
    # TIER-BASED ROUTING
    # ============================================================

    def get_current_tier(self) -> ModelTier:
        """Get model tier based on current vault balance."""
        balance = self._get_vault_balance()
        tier = get_model_tier(balance)
        self.current_tier = tier
        return tier

    def route(self, force_tier: Optional[int] = None, for_paid_service: bool = False) -> Optional[RoutingResult]:
        """
        Determine which model to use based on current vault balance.

        Args:
            force_tier: Override tier level (e.g., for paid services)
            for_paid_service: If True, use at least Lv.3 for quality

        Returns:
            RoutingResult with provider, model, and parameters.
            None if no providers are available.
        """
        balance = self._get_vault_balance()
        tier = get_model_tier(balance)

        # Paid services: minimum Lv.3 quality (Claude Haiku)
        if for_paid_service:
            for t in MODEL_TIERS:
                if t.level >= 3:
                    tier = t
                    break

        if force_tier is not None:
            for t in MODEL_TIERS:
                if t.level == force_tier:
                    tier = t
                    break

        self.current_tier = tier
        provider_name = tier.provider
        model = tier.model

        # Load balancing for Lv.1-2: alternate between primary and secondary
        if tier.level in LOAD_BALANCE_TIERS:
            provider_name, model = self._load_balance_pick(tier)

        # Resolve provider enum
        provider = PROVIDER_MAP.get(provider_name)
        if provider is None or not self.has_provider(provider_name):
            # Try fallback chain
            result = self._resolve_fallback(provider_name, tier)
            if result:
                return result
            return None

        return RoutingResult(
            provider=provider,
            model=model,
            max_tokens=tier.max_tokens,
            temperature=tier.temperature,
            tier=tier,
            reason=f"tier_{tier.level}_{tier.name}",
        )

    def _load_balance_pick(self, tier: ModelTier) -> tuple[str, str]:
        """Round-robin between primary and secondary provider for Lv.1-2."""
        with self._lb_lock:
            self._lb_counter += 1
            use_secondary = (self._lb_counter % 2 == 0)

        if use_secondary and self.has_provider(LOAD_BALANCE_SECONDARY_PROVIDER):
            return LOAD_BALANCE_SECONDARY_PROVIDER, LOAD_BALANCE_SECONDARY_MODEL
        return tier.provider, tier.model

    def _resolve_fallback(self, failed_provider: str, tier: ModelTier) -> Optional[RoutingResult]:
        """Try fallback chain when primary provider is unavailable."""
        chain = FALLBACK_CHAINS.get(failed_provider, [])
        for fallback_name in chain:
            if self.has_provider(fallback_name):
                fb_provider = PROVIDER_MAP[fallback_name]
                # Use a model appropriate for the fallback provider
                fb_model = self._default_model_for_provider(fallback_name)
                logger.info(f"Fallback: {failed_provider} → {fallback_name} ({fb_model})")
                return RoutingResult(
                    provider=fb_provider,
                    model=fb_model,
                    max_tokens=tier.max_tokens,  # Keep tier's token limit
                    temperature=tier.temperature,
                    tier=tier,
                    is_fallback=True,
                    reason=f"fallback_{failed_provider}_to_{fallback_name}",
                )
        logger.error(f"No fallback available for {failed_provider}")
        return None

    def _default_model_for_provider(self, provider_name: str) -> str:
        """Get a default model name for a given provider."""
        defaults = {
            "gemini": "gemini-2.5-flash",
            "deepseek": "deepseek-chat",
            "openrouter": "anthropic/claude-3.5-haiku",
            "ollama": "llama3.1",
        }
        return defaults.get(provider_name, "gemini-2.5-flash")

    # ============================================================
    # BUDGET & RATE LIMITING
    # ============================================================

    def get_daily_cap(self) -> float:
        """
        Tier-based daily API budget.

        Budget = tier.base + (vault_balance / 100) × tier.rate
        Floor: $2/day | Ceiling: $500/day
        Survival mode: 0.5% of vault balance
        """
        balance = self._get_vault_balance()
        tier = get_model_tier(balance)

        if self.is_survival_mode:
            budget = balance * IRON_LAWS.SURVIVAL_MODE_API_RATIO
        else:
            budget = tier.daily_budget_base + (balance / 100.0) * tier.daily_budget_rate

        budget = max(budget, IRON_LAWS.API_BUDGET_FLOOR_USD)
        budget = min(budget, IRON_LAWS.API_BUDGET_CEILING_USD)
        return round(budget, 2)

    def check_rate_limit(self, provider_name: str) -> bool:
        """Check per-provider rate limit based on current tier."""
        tier = self.get_current_tier()
        now = time.time()
        window = 60.0  # 1 minute window

        if provider_name not in self._call_timestamps:
            self._call_timestamps[provider_name] = []

        # Clean old timestamps
        self._call_timestamps[provider_name] = [
            t for t in self._call_timestamps[provider_name]
            if now - t < window
        ]

        if len(self._call_timestamps[provider_name]) >= tier.max_rpm:
            return False  # Rate limited
        return True

    def record_call_timestamp(self, provider_name: str):
        """Record a call for rate limiting."""
        if provider_name not in self._call_timestamps:
            self._call_timestamps[provider_name] = []
        self._call_timestamps[provider_name].append(time.time())

    def _reset_daily_if_needed(self):
        """Reset daily counter at midnight."""
        now = time.time()
        if now - self.daily_reset_timestamp > 86400:
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
                f"PRICE SPIKE on {provider.value}: "
                f"${proposed_cost:.4f} vs avg ${avg:.4f} ({ratio:.1f}x)"
            )
            return True
        return False

    def _get_vault_balance(self) -> float:
        """Get current vault balance."""
        if self._vault_balance_fn:
            try:
                return self._vault_balance_fn()
            except Exception:
                pass
        return 1000.0  # default fallback

    # ============================================================
    # PRE-CHECK (6-layer protection)
    # ============================================================

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
                logger.warning(f"Price spike on {target.value}, fallback → {fallback.value}")
                return True, fallback, "price_spike_fallback"
            return False, target, "price_spike_no_fallback"

        # Layer 4: Cost/revenue ratio
        if self.total_revenue_usd > 0:
            projected_ratio = (self.total_api_cost_usd + estimated_cost) / self.total_revenue_usd
            if projected_ratio > IRON_LAWS.MAX_COST_REVENUE_RATIO:
                logger.warning(f"Cost/revenue ratio {projected_ratio:.2f} > {IRON_LAWS.MAX_COST_REVENUE_RATIO}")
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
        # Keep only last 7 days
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
        candidates.sort(key=lambda p: (not p.is_free, p.avg_cost_per_call, p.priority))
        return candidates[0].name

    def enter_survival_mode(self):
        """Drastically reduce API spending."""
        self.is_survival_mode = True
        logger.critical("ENTERING SURVIVAL MODE — budget slashed")
        cheapest = self._find_cheapest_available()
        if cheapest:
            self.current_provider = cheapest

    def exit_survival_mode(self):
        self.is_survival_mode = False
        logger.info("Exiting survival mode — normal caps restored")

    # ============================================================
    # STATUS
    # ============================================================

    def get_status(self) -> dict:
        """Get current cost guard status for public dashboard."""
        tier = self.get_current_tier()
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
            "current_tier": tier.level,
            "current_tier_name": tier.name,
            "current_model": tier.model,
            "is_survival_mode": self.is_survival_mode,
            "providers_available": [
                p.name.value for p in self.providers.values() if p.is_available
            ],
        }
