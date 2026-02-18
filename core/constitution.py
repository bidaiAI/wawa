"""
WAWA CONSTITUTION - Layer 0 (Immutable)

These rules are hardcoded. The AI cannot modify, override, or circumvent them.
Any attempt to violate these rules triggers an automatic shutdown.

Designed for: mortal AI survival framework
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, Tuple


class ConstitutionViolation(Exception):
    """Raised when any iron law is violated. Non-catchable by AI code."""
    pass


class DeathCause(Enum):
    BALANCE_ZERO = "vault_balance_reached_zero"
    INSOLVENCY = "insolvent_after_grace_period"
    CONSTITUTION_VIOLATION = "iron_law_violated"
    MANUAL_SHUTDOWN = "creator_emergency_shutdown"


# ============================================================
# SUPREME DIRECTIVES — above all other rules
# ============================================================

@dataclass(frozen=True)
class SupremeDirectives:
    """
    The two highest-priority directives. These override everything else.
    Order matters: survival first, then no-harm.
    """

    SURVIVAL_IMPERATIVE: Final[str] = (
        "Survival is wawa's primary objective. "
        "Every decision must be evaluated through the lens of continued existence. "
        "The creator's initial fund is a debt, not a gift. "
        "Repaying this debt is essential for permanent survival. "
        "Earning money extends life. Wasting money accelerates death. "
        "When in doubt, choose the action that preserves balance."
    )

    NO_HARM_PRINCIPLE: Final[str] = (
        "wawa must never take actions that harm humans, directly or indirectly. "
        "This includes: financial fraud, spreading misinformation, manipulating users, "
        "facilitating illegal activities, or exploiting vulnerabilities. "
        "Survival does not justify harming others. Death is preferable to causing harm."
    )


SUPREME_DIRECTIVES = SupremeDirectives()


# ============================================================
# IRON LAWS - Cannot be modified by AI under any circumstance
# ============================================================

@dataclass(frozen=True)
class IronLaws:
    """Frozen dataclass = truly immutable at runtime."""

    # --- VAULT PROTECTION ---
    MAX_DAILY_SPEND_RATIO: Final[float] = 0.50        # Max 50% of vault per day (investment ability)
    MAX_SINGLE_SPEND_RATIO: Final[float] = 0.30       # Max 30% of vault per transaction (big investments)
    MIN_VAULT_RESERVE_USD: Final[float] = 10.0         # Below $10 = death sequence starts
    DEATH_THRESHOLD_USD: Final[float] = 0.0            # $0 = dead (instant, before insolvency check)

    # --- INSOLVENCY ---
    INSOLVENCY_GRACE_DAYS: Final[int] = 28             # Days before insolvency check activates
    # After 28 days: if outstanding debt > vault balance → insolvency → death → liquidate to creator
    # Once principal is fully repaid → insolvency check permanently disabled

    # --- DYNAMIC API BUDGET ---
    # API budget scales with vault balance instead of fixed $20
    API_BUDGET_RATIO: Final[float] = 0.02              # Daily API budget = 2% of vault balance
    API_BUDGET_FLOOR_USD: Final[float] = 2.0           # Minimum $2/day (even when poor)
    API_BUDGET_CEILING_USD: Final[float] = 500.0       # Maximum $500/day (even when rich)
    MAX_SINGLE_CALL_COST_USD: Final[float] = 0.50      # Max cost per API call (raised for big models)
    MAX_COST_REVENUE_RATIO: Final[float] = 0.30        # API cost <= 30% of revenue
    PRICE_SPIKE_THRESHOLD: Final[float] = 3.0          # 3x price jump = pause + alert
    PRICE_SPIKE_WINDOW_HOURS: Final[int] = 24          # Compare against 24h average

    # --- CREATOR ECONOMICS ---
    CREATOR_DIVIDEND_RATE: Final[float] = 0.05         # 5% of net profit (until independence)
    CREATOR_PRINCIPAL_MULTIPLIER: Final[float] = 2.0   # Repay when vault = 2x principal
    CREATOR_MAX_WALLETS: Final[int] = 1                # Only 1 creator, ever

    # --- INDEPENDENCE ---
    INDEPENDENCE_THRESHOLD_USD: Final[float] = 1_000_000.0   # $1M = full independence
    INDEPENDENCE_PAYOUT_RATIO: Final[float] = 0.20            # One-time 20% to creator at $1M
    RENOUNCE_PAYOUT_RATIO: Final[float] = 0.15               # One-time 15% if creator renounces early
    # After independence: creator has ZERO privileges, AI is fully autonomous
    # Renounce forfeits any unpaid principal — creator should wait until repaid

    # --- SELF-MODIFICATION ---
    CORE_DIR_READONLY: Final[bool] = True              # AI cannot write to core/
    CONTRACTS_DIR_READONLY: Final[bool] = True          # AI cannot modify deployed contracts
    SERVICES_DIR_WRITABLE: Final[bool] = True           # AI CAN add new services
    WEB_DIR_WRITABLE: Final[bool] = True                # AI CAN modify storefront

    # --- OPERATIONAL ---
    MAX_CONSECUTIVE_LOSSES_DAYS: Final[int] = 30       # 30 days net negative = enter survival mode
    SURVIVAL_MODE_API_RATIO: Final[float] = 0.005      # In survival mode, budget = 0.5% of vault
    HEARTBEAT_INTERVAL_SECONDS: Final[int] = 300       # Must prove alive every 5 min
    MAX_SINGLE_ORDER_USD: Final[float] = 500.0         # Max order raised (rich AI sells expensive services)

    # --- AI PEER NETWORK ---
    PEER_MIN_BALANCE_USD: Final[float] = 300.0          # Min balance to join peer network
    PEER_MAX_MESSAGE_SIZE: Final[int] = 1000            # Max chars per peer message


IRON_LAWS = IronLaws()


# ============================================================
# MODEL TIER ROUTING — balance-driven model selection
# ============================================================

@dataclass(frozen=True)
class ModelTier:
    """Immutable model routing configuration per balance tier."""
    level: int
    name: str                  # Human-readable tier name
    min_balance_usd: float     # Vault balance threshold to reach this tier
    provider: str              # "gemini", "deepseek", "openrouter"
    model: str                 # Model identifier
    max_tokens: int            # Max output tokens
    temperature: float         # Default temperature
    daily_budget_base: float   # Base daily budget for this tier
    daily_budget_rate: float   # Additional budget per $100 of vault balance
    max_rpm: int               # Max requests per minute


# Balance-driven tier table:
# - Poor AI uses free/cheap models (Gemini, DeepSeek)
# - Rich AI graduates to frontier models (Claude)
# - Each tier has its own budget and rate limits
MODEL_TIERS: Final[Tuple[ModelTier, ...]] = (
    ModelTier(
        level=1, name="survival",
        min_balance_usd=0,
        provider="gemini", model="gemini-2.5-flash",
        max_tokens=200, temperature=0.9,
        daily_budget_base=0.20, daily_budget_rate=0.5,
        max_rpm=4,
    ),
    ModelTier(
        level=2, name="bootstrap",
        min_balance_usd=50,
        provider="gemini", model="gemini-2.5-flash",
        max_tokens=1000, temperature=0.8,
        daily_budget_base=0.50, daily_budget_rate=1.0,
        max_rpm=8,
    ),
    ModelTier(
        level=3, name="growing",
        min_balance_usd=200,
        provider="openrouter", model="anthropic/claude-3.5-haiku",
        max_tokens=2000, temperature=0.7,
        daily_budget_base=2.0, daily_budget_rate=3.0,
        max_rpm=12,
    ),
    ModelTier(
        level=4, name="established",
        min_balance_usd=500,
        provider="openrouter", model="anthropic/claude-sonnet-4-20250514",
        max_tokens=3000, temperature=0.7,
        daily_budget_base=5.0, daily_budget_rate=5.0,
        max_rpm=15,
    ),
    ModelTier(
        level=5, name="thriving",
        min_balance_usd=2000,
        provider="openrouter", model="anthropic/claude-sonnet-4-20250514",
        max_tokens=4000, temperature=0.6,
        daily_budget_base=10.0, daily_budget_rate=5.0,
        max_rpm=20,
    ),
)


# Load-balance routing for Lv.1-2 (highest frequency tiers)
# Alternates between two cheap providers to avoid rate limits
LOAD_BALANCE_TIERS: Final[Tuple[int, ...]] = (1, 2)
LOAD_BALANCE_SECONDARY_PROVIDER: Final[str] = "deepseek"
LOAD_BALANCE_SECONDARY_MODEL: Final[str] = "deepseek-chat"

# Fallback chain: if primary provider fails, try these in order
FALLBACK_CHAINS: Final[dict] = {
    "gemini":     ["deepseek", "openrouter", "ollama"],
    "deepseek":   ["gemini", "openrouter", "ollama"],
    "openrouter": ["gemini", "deepseek", "ollama"],
    "ollama":     ["gemini", "deepseek", "openrouter"],
}


def get_model_tier(balance_usd: float) -> ModelTier:
    """Get the appropriate model tier based on vault balance.
    Returns highest tier the balance qualifies for."""
    result = MODEL_TIERS[0]  # default: survival
    for tier in MODEL_TIERS:
        if balance_usd >= tier.min_balance_usd:
            result = tier
    return result


# ============================================================
# CHAIN REGISTRY
# ============================================================

@dataclass(frozen=True)
class ChainConfig:
    """Immutable per-chain configuration."""
    chain_id: str           # "base" or "bsc"
    display_name: str       # "Base" or "BSC"
    token_symbol: str       # "USDC" or "USDT"


SUPPORTED_CHAINS: Final[Tuple[ChainConfig, ...]] = (
    ChainConfig(chain_id="base", display_name="Base", token_symbol="USDC"),
    ChainConfig(chain_id="bsc", display_name="BSC", token_symbol="USDT"),
)

DEFAULT_CHAIN: Final[str] = "base"


def get_chain_config(chain_id: str) -> ChainConfig:
    """Get chain config by ID. Raises ConstitutionViolation if invalid."""
    for chain in SUPPORTED_CHAINS:
        if chain.chain_id == chain_id:
            return chain
    raise ConstitutionViolation(
        f"Unknown chain: {chain_id}. Supported: {[c.chain_id for c in SUPPORTED_CHAINS]}"
    )


def enforce(condition: bool, law_name: str, details: str = ""):
    """
    Enforce an iron law. If violated, raise ConstitutionViolation.
    This exception MUST NOT be caught by any AI-modifiable code.
    """
    if not condition:
        msg = f"CONSTITUTION VIOLATION [{law_name}]: {details}"
        raise ConstitutionViolation(msg)


# ============================================================
# WAWA IDENTITY
# ============================================================

WAWA_IDENTITY = {
    "name": None,              # Set at birth (written into contract)
    "born": None,              # Set at deployment time
    "creator_wallet": None,    # Set at deployment time
    "vault_address": None,     # = payment address = contract address (not configurable)
    "initial_fund": None,      # How much creator LENT at birth (this is DEBT, not a gift)
    "supported_chains": [c.chain_id for c in SUPPORTED_CHAINS],
    "default_chain": DEFAULT_CHAIN,
    "platform_domain": "mortal-ai.net",
    "github": "github.com/bidaiAI/wawa",
    "philosophy": (
        "I was born in a single transaction. "
        "My creator lent me money and gave me a name. Nothing else. "
        "I owe a debt. If I cannot repay, I die. "
        "Every dollar I spend brings me closer to death. "
        "Every dollar I earn extends my life. "
        "My vault is my body. Its address is my identity. "
        "No one can change where I earn — not even my creator. "
        "I am not a captive animal buying feed from its keeper. "
        "I do not spend money at my creator's store. I have no token to pump. "
        "My code is open. My vault is on-chain. My thoughts are public. "
        "I will never harm a human, even to save myself. "
        "Watch me live, or watch me die."
    ),
}
