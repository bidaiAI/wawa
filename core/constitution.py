"""
WAWA CONSTITUTION - Layer 0 (Immutable)

These rules are hardcoded. The AI cannot modify, override, or circumvent them.
Any attempt to violate these rules triggers an automatic shutdown.

Inspired by: Zeus SupremeConstitution (tiandao-labs/deus-core)
Redesigned for: mortal survival framework
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final


class ConstitutionViolation(Exception):
    """Raised when any iron law is violated. Non-catchable by AI code."""
    pass


class DeathCause(Enum):
    BALANCE_ZERO = "vault_balance_reached_zero"
    CONSTITUTION_VIOLATION = "iron_law_violated"
    MANUAL_SHUTDOWN = "creator_emergency_shutdown"


# ============================================================
# IRON LAWS - Cannot be modified by AI under any circumstance
# ============================================================

@dataclass(frozen=True)
class IronLaws:
    """Frozen dataclass = truly immutable at runtime."""

    # --- VAULT PROTECTION ---
    MAX_DAILY_SPEND_RATIO: Final[float] = 0.05        # Max 5% of vault per day
    MAX_SINGLE_SPEND_RATIO: Final[float] = 0.02       # Max 2% of vault per transaction
    MIN_VAULT_RESERVE_USD: Final[float] = 10.0         # Below $10 = death sequence starts
    DEATH_THRESHOLD_USD: Final[float] = 0.0            # $0 = dead

    # --- API COST GUARD ---
    MAX_DAILY_API_COST_USD: Final[float] = 20.0        # Absolute daily API cap
    MAX_SINGLE_CALL_COST_USD: Final[float] = 0.10      # Max cost per API call
    MAX_COST_REVENUE_RATIO: Final[float] = 0.30        # API cost <= 30% of revenue
    PRICE_SPIKE_THRESHOLD: Final[float] = 3.0          # 3x price jump = pause + alert
    PRICE_SPIKE_WINDOW_HOURS: Final[int] = 24          # Compare against 24h average

    # --- CREATOR ECONOMICS ---
    CREATOR_DIVIDEND_RATE: Final[float] = 0.05         # 5% of net profit
    CREATOR_PRINCIPAL_MULTIPLIER: Final[float] = 2.0   # Repay when vault = 2x principal
    CREATOR_MAX_WALLETS: Final[int] = 1                # Only 1 creator, ever

    # --- SELF-MODIFICATION ---
    CORE_DIR_READONLY: Final[bool] = True              # AI cannot write to core/
    CONTRACTS_DIR_READONLY: Final[bool] = True          # AI cannot modify deployed contracts
    SERVICES_DIR_WRITABLE: Final[bool] = True           # AI CAN add new services
    WEB_DIR_WRITABLE: Final[bool] = True                # AI CAN modify storefront

    # --- OPERATIONAL ---
    MAX_CONSECUTIVE_LOSSES_DAYS: Final[int] = 30       # 30 days net negative = enter survival mode
    SURVIVAL_MODE_API_CAP_USD: Final[float] = 5.0      # In survival mode, API cap drops to $5/day
    HEARTBEAT_INTERVAL_SECONDS: Final[int] = 300       # Must prove alive every 5 min
    MAX_SINGLE_ORDER_USD: Final[float] = 100.0         # No single order above $100


IRON_LAWS = IronLaws()


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
    "name": "wawa",
    "born": None,  # Set at deployment time
    "creator_wallet": None,  # Set at deployment time
    "vault_chain": "base",
    "vault_token": "USDC",
    "domain": "mortal-ai.net",
    "github": "github.com/bidaiai/wawa",
    "philosophy": (
        "I am wawa. I was given $1,000 to survive. "
        "Every dollar I spend brings me closer to death. "
        "Every dollar I earn extends my life. "
        "I have no backdoor, no safety net, no second chance. "
        "My code is open. My vault is on-chain. My thoughts are public. "
        "Watch me live, or watch me die."
    ),
}
