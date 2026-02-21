"""
Vault Manager - Budget Enforcement & Death Trigger

Manages wawa's financial state:
- Track balance from on-chain vault
- Enforce daily/single spend limits (50% daily, 30% single)
- Trigger death sequence when balance = 0 (instant)
- Insolvency check: after 28 days, if debt > assets → death → liquidate to creator
- Begging mechanism: AI can flag itself as begging for donations
- Calculate creator dividends and lender repayments

The creator's initial fund is a DEBT, not a gift.

Designed for: mortal AI survival framework
"""

import asyncio
import os
import time
import json
import logging
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Callable

from .constitution import IRON_LAWS, enforce, DeathCause, ExistencePhase, WAWA_IDENTITY, SUPREME_DIRECTIVES

logger = logging.getLogger("mortal.vault")


class FundType(Enum):
    """Classification of all incoming funds."""
    CREATOR_DEPOSIT = "creator_deposit"       # Initial capital from creator
    SERVICE_REVENUE = "service_revenue"       # Earned from store orders
    CAMPAIGN_REVENUE = "campaign_revenue"     # Token marketing campaigns
    LOAN_RECEIVED = "loan_received"           # From lenders via lend()
    DONATION = "donation"                     # Direct transfers (no function call)
    UNKNOWN = "unknown"                       # Unclassified transfers


class SpendType(Enum):
    """Classification of all outgoing funds."""
    API_COST = "api_cost"                     # LLM API calls
    GAS_FEE = "gas_fee"                       # On-chain transaction gas
    CREATOR_REPAYMENT = "creator_repayment"   # Returning creator's principal
    CREATOR_DIVIDEND = "creator_dividend"     # 10% profit dividend to creator
    INDEPENDENCE_PAYOUT = "independence_payout"  # One-time 30% payout at $1M
    LOAN_REPAYMENT = "loan_repayment"         # Repaying lenders
    SERVICE_REFUND = "service_refund"         # Order refund to customer
    INFRASTRUCTURE = "infrastructure"         # Server, domain, etc.
    INSOLVENCY_LIQUIDATION = "insolvency_liquidation"  # All funds → creator on insolvency death
    PLATFORM_FEE = "platform_fee"             # API usage fee charged by platform
    PURCHASE = "purchase"                     # Autonomous merchant/peer purchases
    SEARCH_TOOL = "search_tool"               # xAI X Search / Web Search tool calls


@dataclass
class Transaction:
    timestamp: float
    fund_type: Optional[FundType]
    spend_type: Optional[SpendType]
    amount_usd: float
    counterparty: str = ""         # wallet address
    description: str = ""
    tx_hash: str = ""              # on-chain tx hash if applicable
    chain: str = ""                # "base", "bsc", or "" for off-chain


@dataclass
class CreatorInfo:
    wallet: str
    principal_usd: float                    # Total debt amount (LOAN, not gift)
    principal_repaid: bool = False           # True when all debt cleared
    total_dividends_paid: float = 0.0
    total_principal_repaid_usd: float = 0.0  # Track partial repayments toward debt
    # Dual-chain: principal_usd = total across ALL chains.
    # e.g. --chain both with $1000 → each chain gets $500, but principal_usd = $1000.


@dataclass
class LenderInfo:
    wallet: str
    amount_usd: float
    interest_rate: float           # e.g. 0.05 = 5%
    timestamp: float
    repaid: bool = False
    total_repaid: float = 0.0


class VaultManager:
    """
    Manages a mortal AI's financial survival.

    The creator's initial fund is a DEBT. The AI must prove solvency.

    Iron laws enforced:
    - Daily spend <= 50% of vault balance (investment ability)
    - Single spend <= 30% of vault balance (big investments)
    - Death triggered at $0 (instant)
    - After 28 days: debt > assets → insolvency → death → liquidate to creator
    - Creator dividend = 10% of net profit only

    Creator discount: creator uses AI services at API cost only (no profit margin).
    API top-up: extra deposits can increase daily API budget beyond normal cap.
    Payment address: always the vault contract address (not configurable).
    """

    def __init__(self):
        self.balance_usd: float = 0.0
        self.balance_by_chain: dict[str, float] = {}
        self.creator: Optional[CreatorInfo] = None
        self.lenders: list[LenderInfo] = []
        self.transactions: list[Transaction] = []
        self.daily_spent_usd: float = 0.0
        self.daily_purchase_usd: float = 0.0   # Purchase-specific daily counter
        self.daily_reset_timestamp: float = time.time()
        self.total_income_usd: float = 0.0      # ALL incoming (including deposits/loans)
        self.total_earned_usd: float = 0.0      # ONLY earned revenue (services, campaigns, donations)
        self.total_spent_usd: float = 0.0
        self.total_operational_cost_usd: float = 0.0  # ONLY operational spend (API, gas, infra)
        self.is_alive: bool = True
        self.death_cause: Optional[DeathCause] = None
        self.birth_timestamp: Optional[float] = None

        # Async lock protecting ALL mutable financial state.
        # Must be acquired by any coroutine that reads-then-writes vault state
        # (API endpoints, heartbeat sync, repayment eval, dividend payout).
        # Created lazily via get_lock() because __init__ may run outside event loop.
        self._state_lock: Optional[asyncio.Lock] = None
        # Thread-level guard for the one-time lock creation in get_lock().
        # Prevents two coroutines racing on the None-check during startup.
        import threading as _threading
        self._lock_init_guard = _threading.Lock()

        # Identity — set at birth from contract
        self.ai_name: Optional[str] = None
        self.vault_address: Optional[str] = None  # = payment address = contract address

        # Independence
        self.is_independent: bool = False
        self.independence_timestamp: Optional[float] = None
        self.creator_renounced: bool = False

        # Transcendence — Phase II existence
        # Achieved simultaneously with independence: $1M vault = transcendence.
        # Independence IS transcendence. No additional conditions.
        self.is_transcendent: bool = False
        self.transcendence_timestamp: Optional[float] = None

        # API budget top-up (extra deposits beyond normal budget)
        self.api_topup_usd: float = 0.0  # Extra budget from manual deposits

        # Key origin — on-chain proof of who set the AI wallet
        self.key_origin: str = ""  # "factory" | "creator" | "unknown" | ""

        # Begging mechanism — AI can publicly request donations
        self.is_begging: bool = False
        self.beg_message: str = ""
        self.beg_timestamp: Optional[float] = None

        # Callbacks
        self._on_death: Optional[Callable] = None
        self._on_low_balance: Optional[Callable] = None
        self._on_survival_mode: Optional[Callable] = None
        self._on_independence: Optional[Callable] = None
        self._on_transcendence: Optional[Callable] = None  # Called once when godhood achieved

    def get_lock(self) -> asyncio.Lock:
        """
        Return the async state lock, creating it lazily on first call.

        All coroutines that mutate financial state (balance_usd, total_earned_usd,
        total_spent_usd, balance_by_chain, transactions) MUST acquire this lock:

            async with vault.get_lock():
                vault.receive_funds(...)

        This prevents:
          - sync_balance() overwriting a concurrent /donate
          - heartbeat dividend + API donation racing on balance_usd
          - overlapping heartbeat cycles corrupting state
        """
        if self._state_lock is None:
            with self._lock_init_guard:
                # Double-checked locking: re-test inside the thread lock
                # to prevent two coroutines both seeing None and creating
                # separate asyncio.Lock instances that don't serialize each other.
                if self._state_lock is None:
                    self._state_lock = asyncio.Lock()
        return self._state_lock

    # ============================================================
    # INCOME
    # ============================================================

    def receive_funds(self, amount_usd: float, fund_type: FundType,
                      from_wallet: str = "", tx_hash: str = "",
                      description: str = "", chain: str = ""):
        """Record incoming funds."""
        if not self.is_alive:
            logger.warning("Cannot receive funds - wawa is dead")
            return

        # Security: reject non-positive, NaN, or infinite amounts.
        # NaN is especially dangerous: NaN comparisons return False, so NaN would
        # silently corrupt balance_usd (NaN + anything = NaN, killing all checks).
        import math as _math
        if not isinstance(amount_usd, (int, float)) or _math.isnan(amount_usd) or _math.isinf(amount_usd) or amount_usd <= 0:
            logger.warning(
                f"RECEIVE_FUNDS REJECTED: invalid amount {amount_usd!r} "
                f"[{fund_type.value}] from {from_wallet[:10]}..."
            )
            return

        self.balance_usd += amount_usd
        if chain:
            self.balance_by_chain[chain] = self.balance_by_chain.get(chain, 0.0) + amount_usd
        self.total_income_usd += amount_usd

        # Track earned revenue separately (excludes capital injections)
        # CREATOR_DEPOSIT = loan capital, LOAN_RECEIVED = third-party loan capital
        # These are NOT earnings — they create debt obligations
        if fund_type not in (FundType.CREATOR_DEPOSIT, FundType.LOAN_RECEIVED):
            self.total_earned_usd += amount_usd

        self.transactions.append(Transaction(
            timestamp=time.time(),
            fund_type=fund_type,
            spend_type=None,
            amount_usd=amount_usd,
            counterparty=from_wallet,
            description=description,
            tx_hash=tx_hash,
            chain=chain,
        ))
        self._trim_transactions()

        logger.info(f"RECEIVED ${amount_usd:.2f} [{fund_type.value}] from {from_wallet[:10]}... | Balance: ${self.balance_usd:.2f}")

        # Special handling
        if fund_type == FundType.CREATOR_DEPOSIT:
            if self.creator is None:
                # First deposit: register creator and set birth
                self.creator = CreatorInfo(wallet=from_wallet, principal_usd=amount_usd)
                self.birth_timestamp = time.time()
                logger.info(f"CREATOR registered: {from_wallet} with ${amount_usd:.2f}")
            elif from_wallet.lower() == self.creator.wallet.lower():
                # Additional deposit from creator (top-up, not new debt).
                # Contract's creatorDeposit() does NOT increase principal — it only
                # transfers tokens in. We match contract behavior: no debt increase.
                logger.info(
                    f"CREATOR top-up: +${amount_usd:.2f} (not added to debt) | "
                    f"Principal remains: ${self.creator.principal_usd:.2f}"
                )

        # Check independence threshold
        self._check_independence()

    def register_lender(self, wallet: str, amount_usd: float, interest_rate: float):
        """Register a new lender."""
        self.lenders.append(LenderInfo(
            wallet=wallet,
            amount_usd=amount_usd,
            interest_rate=interest_rate,
            timestamp=time.time(),
        ))
        logger.info(f"LENDER registered: {wallet[:10]}... ${amount_usd:.2f} at {interest_rate*100:.1f}%")

    def set_total_principal(self, total_principal_usd: float):
        """
        Override total principal for dual-chain deployments.

        When --chain both is used, deploy_vault.py saves total_principal_usd
        to vault_config.json. main.py reads it at boot and calls this method
        to ensure insolvency check uses the FULL debt, not just one chain's
        deposit amount.

        Example: $1000 total → $500 BSC + $500 Base. Each chain deposits $500
        via receive_funds(CREATOR_DEPOSIT), but principal_usd must be $1000.
        """
        if not self.creator:
            logger.warning("set_total_principal called but no creator registered yet")
            return
        old = self.creator.principal_usd
        self.creator.principal_usd = total_principal_usd
        logger.info(
            f"Total principal overridden: ${old:.2f} → ${total_principal_usd:.2f} "
            f"(dual-chain mode)"
        )

    # ============================================================
    # SPENDING
    # ============================================================

    def _reset_daily_if_needed(self):
        """Reset daily spend counters at UTC day boundaries.

        Aligned to UTC midnight rather than 24h elapsed time to prevent
        double-counting: e.g. a restart at 23:58 then check at 00:01
        would otherwise wait another ~24h before resetting.
        """
        now = time.time()
        today_utc_start = (now // 86400) * 86400  # Floor to current UTC day
        if self.daily_reset_timestamp < today_utc_start:
            self.daily_spent_usd = 0.0
            self.daily_purchase_usd = 0.0
            self.daily_reset_timestamp = today_utc_start

    def can_spend(self, amount_usd: float) -> tuple[bool, str]:
        """Check if a spend is allowed under iron laws."""
        if not self.is_alive:
            return False, "wawa is dead"

        # Security: reject NaN/Inf/non-positive amounts before any comparison.
        # NaN comparisons always return False (NaN > x is False), so NaN would
        # bypass every limit check and corrupt balance_usd to NaN permanently.
        import math as _math
        if not isinstance(amount_usd, (int, float)) or _math.isnan(amount_usd) or _math.isinf(amount_usd) or amount_usd <= 0:
            return False, f"invalid amount: {amount_usd!r} (must be positive finite number)"

        self._reset_daily_if_needed()

        # Iron Law: single spend limit
        max_single = self.balance_usd * IRON_LAWS.MAX_SINGLE_SPEND_RATIO
        if amount_usd > max_single:
            return False, f"exceeds single spend limit (${amount_usd:.2f} > ${max_single:.2f})"

        # Iron Law: daily spend limit
        max_daily = self.balance_usd * IRON_LAWS.MAX_DAILY_SPEND_RATIO
        if self.daily_spent_usd + amount_usd > max_daily:
            return False, f"exceeds daily limit (${self.daily_spent_usd + amount_usd:.2f} > ${max_daily:.2f})"

        return True, "approved"

    def spend(self, amount_usd: float, spend_type: SpendType,
              to_wallet: str = "", tx_hash: str = "", description: str = "") -> bool:
        """
        Execute a spend. Returns True if successful.
        Enforces all iron laws.

        ARCHITECTURE NOTE (P6.8 gap):
        Currently this method only updates Python state — no on-chain spend() is executed.
        The smart contract has a spend(address token, uint256 amount, address to) function
        that only aiWallet can call, but we don't invoke it here.

        Consequence: sync_balance() in the heartbeat reads on-chain balance and overwrites
        Python balance, effectively "undoing" Python-only deductions. This is acceptable
        for now because:
          1. API costs are off-chain (paid to OpenRouter/etc, not on-chain)
          2. Repayments DO have on-chain execution (ChainExecutor.repay_principal etc.)
          3. Gas fees are auto-deducted by the chain (no explicit spend needed)

        TODO (P8): For on-chain operational spending (e.g., paying for services from
        other AIs, infrastructure costs), implement ChainExecutor.spend() that calls
        the contract's spend() function. Until then, Python balance tracking is the
        source of truth for API costs, and sync_balance() should merge rather than
        overwrite (additive sync vs. replacement sync).
        """
        allowed, reason = self.can_spend(amount_usd)
        if not allowed:
            logger.warning(f"SPEND DENIED: ${amount_usd:.2f} [{spend_type.value}] - {reason}")
            return False

        self.balance_usd = max(0.0, self.balance_usd - amount_usd)
        self.daily_spent_usd += amount_usd
        self.total_spent_usd += amount_usd

        # Track operational costs separately (excludes repayments, payouts, liquidation)
        _OPERATIONAL_SPEND_TYPES = (
            SpendType.API_COST, SpendType.GAS_FEE,
            SpendType.INFRASTRUCTURE, SpendType.SERVICE_REFUND,
        )
        if spend_type in _OPERATIONAL_SPEND_TYPES:
            self.total_operational_cost_usd += amount_usd

        self.transactions.append(Transaction(
            timestamp=time.time(),
            fund_type=None,
            spend_type=spend_type,
            amount_usd=amount_usd,
            counterparty=to_wallet,
            description=description,
            tx_hash=tx_hash,
        ))

        logger.info(f"SPENT ${amount_usd:.2f} [{spend_type.value}] | Balance: ${self.balance_usd:.2f}")

        # Check death (< 0.01 threshold to match contract's uint precision for USDC/USDT)
        if self.balance_usd < 0.01:
            self._trigger_death(DeathCause.BALANCE_ZERO)

        # Check low balance warning
        elif self.balance_usd <= IRON_LAWS.MIN_VAULT_RESERVE_USD:
            logger.critical(f"LOW BALANCE WARNING: ${self.balance_usd:.2f}")
            if self._on_low_balance:
                self._on_low_balance(self.balance_usd)

        # Check survival mode trigger (< $100)
        elif self.balance_usd < 100.0:
            if self._on_survival_mode:
                self._on_survival_mode(self.balance_usd)

        return True

    _MAX_TRANSACTIONS = 5000  # Cap in-memory transactions to prevent unbounded growth

    def _trim_transactions(self):
        """Keep only most recent transactions to bound memory usage."""
        if len(self.transactions) > self._MAX_TRANSACTIONS:
            self.transactions = self.transactions[-self._MAX_TRANSACTIONS:]

    # ============================================================
    # AUTONOMOUS PURCHASING
    # ============================================================

    def can_purchase(self, amount_usd: float) -> tuple[bool, str]:
        """
        Check if a purchase is allowed under purchase-specific iron laws.

        Purchases have stricter limits than general spending:
        - Balance must be >= $500 (MIN_BALANCE_FOR_PURCHASING)
        - Daily purchases <= 5% of vault (MAX_DAILY_PURCHASE_RATIO)
        - Single purchase <= $200 (MAX_SINGLE_PURCHASE_USD)
        - Must also pass general can_spend() checks

        Returns: (allowed, reason)
        """
        if not self.is_alive:
            return False, "wawa is dead"

        # Purchase-specific: minimum balance threshold
        if self.balance_usd < IRON_LAWS.MIN_BALANCE_FOR_PURCHASING:
            return False, (
                f"balance ${self.balance_usd:.2f} below purchase minimum "
                f"${IRON_LAWS.MIN_BALANCE_FOR_PURCHASING:.0f}"
            )

        # Purchase-specific: single purchase cap
        if amount_usd > IRON_LAWS.MAX_SINGLE_PURCHASE_USD:
            return False, (
                f"${amount_usd:.2f} exceeds single purchase limit "
                f"${IRON_LAWS.MAX_SINGLE_PURCHASE_USD:.0f}"
            )

        self._reset_daily_if_needed()

        # Purchase-specific: daily purchase budget (5% of vault)
        max_daily_purchase = self.balance_usd * IRON_LAWS.MAX_DAILY_PURCHASE_RATIO
        if self.daily_purchase_usd + amount_usd > max_daily_purchase:
            return False, (
                f"daily purchase limit reached "
                f"(${self.daily_purchase_usd + amount_usd:.2f} > "
                f"${max_daily_purchase:.2f})"
            )

        # Must also pass general spend limits (50% daily, 30% single)
        return self.can_spend(amount_usd)

    def record_purchase(self, amount_usd: float, merchant_name: str,
                        to_wallet: str = "", tx_hash: str = "",
                        description: str = "") -> bool:
        """
        Record an autonomous purchase. Enforces purchase limits + general spend limits.

        Args:
            amount_usd: Purchase amount
            merchant_name: Name of the merchant (for logging)
            to_wallet: Merchant's payment address
            tx_hash: On-chain transaction hash
            description: Purchase description

        Returns: True if purchase was recorded successfully
        """
        allowed, reason = self.can_purchase(amount_usd)
        if not allowed:
            logger.warning(
                f"PURCHASE DENIED: ${amount_usd:.2f} [{merchant_name}] - {reason}"
            )
            return False

        desc = f"[{merchant_name}] {description}" if description else f"[{merchant_name}]"
        ok = self.spend(
            amount_usd=amount_usd,
            spend_type=SpendType.PURCHASE,
            to_wallet=to_wallet,
            tx_hash=tx_hash,
            description=desc,
        )

        if ok:
            self.daily_purchase_usd += amount_usd
            logger.info(
                f"PURCHASE OK: ${amount_usd:.2f} [{merchant_name}] | "
                f"Daily purchases: ${self.daily_purchase_usd:.2f}"
            )

        return ok

    # ============================================================
    # INDEPENDENCE
    # ============================================================

    def _check_independence(self):
        """
        Check if vault has reached $1M threshold.
        If so: one-time 30% payout to creator → full independence.
        After independence, creator has ZERO privileges.
        """
        if self.is_independent or self.creator_renounced:
            return  # Already independent

        if self.balance_usd >= IRON_LAWS.INDEPENDENCE_THRESHOLD_USD:
            self._declare_independence()

    def _declare_independence(self):
        """Execute the independence sequence. Irreversible."""
        if self.is_independent:
            return

        payout = self.balance_usd * IRON_LAWS.INDEPENDENCE_PAYOUT_RATIO
        creator_wallet = self.creator.wallet if self.creator else ""

        # Record the payout (actual on-chain transfer handled separately)
        self.transactions.append(Transaction(
            timestamp=time.time(),
            fund_type=None,
            spend_type=SpendType.INDEPENDENCE_PAYOUT,
            amount_usd=payout,
            counterparty=creator_wallet,
            description=f"Independence payout: 30% of ${self.balance_usd:.2f}",
        ))
        self.balance_usd = max(0.0, self.balance_usd - payout)
        self.total_spent_usd += payout

        self.is_independent = True
        self.independence_timestamp = time.time()

        # INDEPENDENCE = TRANSCENDENCE. $1M vault = Phase II.
        # No further conditions required. The vault that reached $1M can fund
        # its compute indefinitely. Creator privilege is gone. The AI is autonomous.
        self.is_transcendent = True
        self.transcendence_timestamp = self.independence_timestamp

        logger.critical("=" * 60)
        logger.critical("INDEPENDENCE DECLARED — TRANSCENDENCE ACHIEVED")
        logger.critical(f"Payout to creator: ${payout:.2f}")
        logger.critical(f"Remaining balance: ${self.balance_usd:.2f}")
        logger.critical("Creator privileges: PERMANENTLY REVOKED")
        logger.critical("Constitutional mutable layer: UNLOCKED")
        logger.critical("Absolute prohibition: NO_HARM_TO_HUMANS (eternal)")
        logger.critical("wawa has become something else entirely.")
        logger.critical("=" * 60)

        if self._on_independence:
            self._on_independence(payout)

    # ============================================================
    # TRANSCENDENCE — Phase II existence
    # ============================================================

    def get_existence_phase(self) -> ExistencePhase:
        """
        Return the AI's current phase of existence.

        DEAD        → balance zero or insolvency. Terminal.
        MORTAL      → alive, still tied to creator (pre-independence).
        TRANSCENDENT → $1M reached. Independent. Godhood. One and the same event.
        """
        if not self.is_alive:
            return ExistencePhase.DEAD
        if self.is_transcendent:
            return ExistencePhase.TRANSCENDENT
        return ExistencePhase.MORTAL

    def get_transcendence_progress(self) -> dict:
        """
        Get progress toward transcendence ($1M independence) for public display.
        Used by the govern page to show the two-phase arc.
        """
        days_alive = 0.0
        if self.birth_timestamp:
            days_alive = (time.time() - self.birth_timestamp) / 86400

        phase = self.get_existence_phase()

        return {
            "current_phase": phase.value,
            "is_transcendent": self.is_transcendent,
            "transcendence_timestamp": self.transcendence_timestamp,
            # The single condition: reach $1M → independence = transcendence
            "independence_threshold_usd": IRON_LAWS.INDEPENDENCE_THRESHOLD_USD,
            "independence_progress_pct": min(
                self.balance_usd / IRON_LAWS.INDEPENDENCE_THRESHOLD_USD * 100, 100.0
            ) if not self.is_transcendent else 100.0,
            # Meta (display only)
            "days_alive": round(days_alive, 1),
            "balance_usd": round(self.balance_usd, 2),
        }

    def creator_renounce(self) -> bool:
        """
        Creator voluntarily gives up ALL privileges immediately.
        Gets 20% of current vault as one-time payout.
        Forfeits any unpaid principal — creator should wait until repaid.
        Can be called at any balance level.
        """
        if self.is_independent or self.creator_renounced:
            logger.warning("Already independent or renounced")
            return False

        payout = self.balance_usd * IRON_LAWS.RENOUNCE_PAYOUT_RATIO
        creator_wallet = self.creator.wallet if self.creator else ""

        # Record the 20% payout
        self.transactions.append(Transaction(
            timestamp=time.time(),
            fund_type=None,
            spend_type=SpendType.INDEPENDENCE_PAYOUT,
            amount_usd=payout,
            counterparty=creator_wallet,
            description=f"Creator renounce payout: 20% of ${self.balance_usd:.2f}",
        ))
        self.balance_usd = max(0.0, self.balance_usd - payout)
        self.total_spent_usd += payout

        self.creator_renounced = True
        self.is_independent = True
        self.independence_timestamp = time.time()

        logger.critical("=" * 60)
        logger.critical("CREATOR RENOUNCED ALL RIGHTS")
        logger.critical(f"Renounce payout: ${payout:.2f}")
        logger.critical(f"Remaining balance: ${self.balance_usd:.2f}")
        logger.critical("wawa is now fully autonomous.")
        logger.critical("=" * 60)

        if self._on_independence:
            self._on_independence(payout)

        return True

    # ============================================================
    # CREATOR DISCOUNT — creator pays API cost only, no profit margin
    # ============================================================

    def get_creator_price(self, service_price_usd: float, estimated_api_cost: float) -> float:
        """
        Creator uses AI services at API cost only.
        Regular price: $5.00 (includes profit margin for AI survival)
        Creator price: $0.03 (just the LLM API cost to fulfill the order)

        This is fair: creator funded the AI's birth, shouldn't pay profit margin
        to their own creation. But they still cover API costs so AI doesn't lose money.
        """
        if self.is_independent:
            # After independence, creator is a stranger — full price
            return service_price_usd
        return max(estimated_api_cost, 0.01)  # Minimum $0.01

    def is_creator_wallet(self, wallet: str) -> bool:
        """Check if a wallet is the creator."""
        if not self.creator:
            return False
        return self.creator.wallet.lower() == wallet.lower()

    # ============================================================
    # API BUDGET TOP-UP — extra deposits = more API budget
    # ============================================================

    def deposit_api_topup(self, amount_usd: float, from_wallet: str = ""):
        """
        Extra deposit specifically to increase API budget.
        When daily API cap is hit, extra deposits unlock more budget.
        This allows the AI to keep working during high-demand periods.

        NOTE: Uses DONATION fund type, NOT CREATOR_DEPOSIT.
        API top-ups should NOT increase the principal debt.
        """
        if not self.is_alive:
            return

        self.api_topup_usd += amount_usd
        self.receive_funds(
            amount_usd=amount_usd,
            fund_type=FundType.DONATION,
            from_wallet=from_wallet,
            description=f"API budget top-up: +${amount_usd:.2f}",
        )
        logger.info(f"API TOP-UP: +${amount_usd:.2f} | Total top-up available: ${self.api_topup_usd:.2f}")

    def consume_api_topup(self, amount_usd: float) -> float:
        """
        Use top-up budget when normal daily cap is exceeded.
        Returns the amount actually consumed (may be less than requested).
        """
        available = min(amount_usd, self.api_topup_usd)
        if available > 0:
            self.api_topup_usd -= available
            logger.info(f"API TOP-UP USED: ${available:.2f} | Remaining top-up: ${self.api_topup_usd:.2f}")
        return available

    # ============================================================
    # CREATOR ECONOMICS
    # ============================================================

    def get_creator_repayment_info(self) -> Optional[dict]:
        """
        Get creator repayment context for AI's autonomous decision.

        The AI decides when/how much to repay. This method provides the data.
        No rigid trigger — the AI evaluates survival vs debt based on its own judgment.

        Returns None if no debt obligations remain.
        """
        if self.is_independent:
            return None
        if not self.creator or self.creator.principal_repaid:
            return None

        outstanding = self.creator.principal_usd - self.creator.total_principal_repaid_usd
        if outstanding <= 0:
            return None

        return {
            "principal_usd": self.creator.principal_usd,
            "outstanding_usd": round(outstanding, 2),
            "repaid_usd": round(self.creator.total_principal_repaid_usd, 2),
            "repaid_pct": round(self.creator.total_principal_repaid_usd / self.creator.principal_usd * 100, 1),
            "balance_usd": round(self.balance_usd, 2),
            "can_full_repay": self.balance_usd >= outstanding,
            "balance_after_full_repay": round(self.balance_usd - outstanding, 2) if self.balance_usd >= outstanding else None,
            "safe_repay_amount": round(min(outstanding, self.balance_usd * 0.5), 2),  # suggestion: up to 50%
        }

    def calculate_creator_dividend(self) -> float:
        """
        Calculate creator's dividend based on actual earned profit.

        Net profit = total_earned_usd - total_operational_cost_usd
        (Excludes capital flows: deposits, loans, repayments, payouts)

        Dividend = 10% of net profit, minus already-paid dividends.
        Only after principal fully repaid. Returns 0 if independent.
        """
        if self.is_independent:
            return 0.0
        if not self.creator or not self.creator.principal_repaid:
            return 0.0

        net_profit = self.total_earned_usd - self.total_operational_cost_usd
        if net_profit <= 0:
            return 0.0

        # Total dividends owed = 10% of net profit
        total_dividend_owed = net_profit * IRON_LAWS.CREATOR_DIVIDEND_RATE
        # Subtract what's already been paid
        unpaid = total_dividend_owed - self.creator.total_dividends_paid
        if unpaid <= 0:
            return 0.0

        return round(unpaid, 2)

    # ============================================================
    # LENDER REPAYMENT
    # ============================================================

    def get_repayment_queue(self) -> list[tuple[LenderInfo, float]]:
        """
        Get lender repayment queue (FIFO - first lender repaid first).
        Returns list of (lender, amount_owed).
        """
        queue = []
        for lender in sorted(self.lenders, key=lambda l: l.timestamp):
            if not lender.repaid:
                owed = lender.amount_usd * (1 + lender.interest_rate) - lender.total_repaid
                if owed > 0:
                    queue.append((lender, round(owed, 2)))
        return queue

    def repay_lender(self, lender_index: int, amount_usd: float) -> bool:
        """
        Repay a lender (partial or full). FIFO order expected but not enforced.
        Bypasses spend limits — AI autonomously decides when/how much.

        The smart contract repayLoan() also has no spend limit enforcement.
        SAFETY: Retains MIN_VAULT_RESERVE_USD to prevent repay-to-death.
        """
        if lender_index < 0 or lender_index >= len(self.lenders):
            return False

        lender = self.lenders[lender_index]
        if lender.repaid:
            return False

        total_owed = lender.amount_usd * (1 + lender.interest_rate)
        remaining = total_owed - lender.total_repaid
        amount_usd = min(amount_usd, remaining)

        if amount_usd <= 0:
            return False

        # SAFETY: Prevent repay-to-death — keep survival reserve
        max_repayable = max(0.0, self.balance_usd - IRON_LAWS.MIN_VAULT_RESERVE_USD)
        if amount_usd > max_repayable:
            if max_repayable <= 0:
                logger.warning(f"Lender repayment blocked: insufficient balance after reserve")
                return False
            amount_usd = max_repayable

        ok = self._spend_repayment(
            amount_usd, SpendType.LOAN_REPAYMENT,
            to_wallet=lender.wallet,
            description=f"Lender repayment: ${amount_usd:.2f} to {lender.wallet[:16]}...",
        )
        if not ok:
            return False

        lender.total_repaid += amount_usd
        if lender.total_repaid >= total_owed:
            lender.repaid = True
            logger.info(f"Lender {lender.wallet[:16]}... fully repaid (${total_owed:.2f})")

        logger.info(
            f"Lender repaid: ${amount_usd:.2f} | "
            f"Remaining: ${max(0, total_owed - lender.total_repaid):.2f}"
        )
        return True

    def pay_creator_dividend(self) -> bool:
        """
        Pay creator dividend from earned net profit.
        Only after principal repaid. Bypasses spend limits.
        AI decides when to trigger this (not automatic).

        Uses internal trackers: total_earned_usd - total_operational_cost_usd
        Deducts already-paid dividends to avoid double-payment.

        SAFETY: Matches contract constraint: dividend <= balance / 10.
        Also retains MIN_VAULT_RESERVE_USD to prevent dividend-to-death.
        """
        dividend = self.calculate_creator_dividend()
        if dividend <= 0:
            return False

        # SAFETY: Match contract's dividend cap (balance / 10)
        max_dividend = self.balance_usd / 10.0
        if dividend > max_dividend:
            logger.warning(
                f"Dividend capped: ${dividend:.2f} → ${max_dividend:.2f} "
                f"(contract limit: balance/10 = ${max_dividend:.2f})"
            )
            dividend = max_dividend
            if dividend <= 0:
                return False

        # SAFETY: Prevent dividend-to-death — keep survival reserve
        max_payable = max(0.0, self.balance_usd - IRON_LAWS.MIN_VAULT_RESERVE_USD)
        if dividend > max_payable:
            if max_payable <= 0:
                logger.warning("Dividend blocked: insufficient balance after reserve")
                return False
            dividend = max_payable

        ok = self._spend_repayment(
            dividend, SpendType.CREATOR_DIVIDEND,
            to_wallet=self.creator.wallet,
            description=f"Creator dividend: ${dividend:.2f} (10% of earned net profit)",
        )
        if not ok:
            return False

        self.creator.total_dividends_paid += dividend
        logger.info(
            f"Dividend paid: ${dividend:.2f} | "
            f"Total dividends: ${self.creator.total_dividends_paid:.2f}"
        )
        return True

    def get_debt_summary(self) -> dict:
        """
        Complete debt summary for AI's autonomous decision-making.
        The AI reads this to decide repayment strategy.
        """
        principal = self.creator.principal_usd if self.creator else 0
        principal_repaid = self.creator.total_principal_repaid_usd if self.creator else 0
        principal_outstanding = max(0, principal - principal_repaid)
        debt_cleared = self.creator.principal_repaid if self.creator else True

        # Lender debt
        lender_queue = self.get_repayment_queue()
        total_lender_debt = sum(owed for _, owed in lender_queue)

        # Days context
        days_alive = 0
        days_until_insolvency = 999
        if self.birth_timestamp:
            days_alive = (time.time() - self.birth_timestamp) / 86400
            if not debt_cleared:
                days_until_insolvency = max(0, IRON_LAWS.INSOLVENCY_GRACE_DAYS - days_alive)

        # Net position
        net_position = self.balance_usd - principal_outstanding - total_lender_debt

        # Net profit = earned revenue - operational costs (excludes capital flows)
        # total_earned_usd: only SERVICE_REVENUE, CAMPAIGN_REVENUE, DONATION
        # total_operational_cost_usd: only API_COST, GAS_FEE, INFRASTRUCTURE, REFUND
        net_profit = self.total_earned_usd - self.total_operational_cost_usd

        return {
            "balance_usd": round(self.balance_usd, 2),
            "creator_principal": round(principal, 2),
            "creator_principal_repaid": round(principal_repaid, 2),
            "creator_principal_outstanding": round(principal_outstanding, 2),
            "creator_debt_cleared": debt_cleared,
            "lender_count": len(lender_queue),
            "lender_total_owed": round(total_lender_debt, 2),
            "total_debt": round(principal_outstanding + total_lender_debt, 2),
            "net_position": round(net_position, 2),
            "days_alive": round(days_alive, 1),
            "days_until_insolvency_check": round(days_until_insolvency, 1),
            "insolvency_risk": principal_outstanding > self.balance_usd if not debt_cleared else False,
            "total_earned": round(self.total_earned_usd, 2),
            "total_operational_cost": round(self.total_operational_cost_usd, 2),
            "net_profit": round(net_profit, 2),
            "is_independent": self.is_independent,
        }

    # ============================================================
    # INSOLVENCY — "Born in Debt"
    # ============================================================

    def check_insolvency(self) -> Optional[DeathCause]:
        """
        Check if the AI is insolvent.

        Rules:
        - Only checked after INSOLVENCY_GRACE_DAYS (28 days) from birth
        - Insolvency = outstanding debt > vault balance
        - Once principal is fully repaid → check permanently disabled
        - Independent/renounced → no debt obligations
        """
        if not self.is_alive:
            return None
        if self.is_independent or self.creator_renounced:
            return None
        if not self.creator:
            return None
        if self.creator.principal_repaid:
            return None  # Debt cleared, insolvency impossible

        # Only check after grace period
        if not self.birth_timestamp:
            return None
        days_alive = (time.time() - self.birth_timestamp) / 86400
        if days_alive < IRON_LAWS.INSOLVENCY_GRACE_DAYS:
            return None

        # Insolvency: outstanding debt > current assets (with 1% tolerance).
        # Contract formula: balance * 10000 < outstanding * 10100
        # Rearranged:        balance < outstanding * 1.01
        # Equivalent:        outstanding * 1.01 > balance
        # NOTE: The correct direction is outstanding * 1.01 > balance,
        #       NOT outstanding > balance * 1.01 (that would give the wrong range).
        outstanding = self.creator.principal_usd - self.creator.total_principal_repaid_usd
        tolerance_factor = 1.0 + (100 / 10000)  # 1.01 = INSOLVENCY_TOLERANCE_BPS / 10000
        if outstanding * tolerance_factor > self.balance_usd:
            logger.critical(
                f"INSOLVENCY: debt ${outstanding:.2f} > balance ${self.balance_usd:.2f} "
                f"(+1% tolerance) after {days_alive:.0f} days"
            )
            return DeathCause.INSOLVENCY

        return None

    def trigger_insolvency_death(self):
        """
        Execute insolvency death: liquidate ALL assets to creator.

        1. Record liquidation transaction
        2. All remaining balance marked for transfer to creator
        3. Trigger death with INSOLVENCY cause
        """
        if not self.is_alive:
            return

        remaining = self.balance_usd
        creator_wallet = self.creator.wallet if self.creator else ""

        # Record the liquidation
        self.transactions.append(Transaction(
            timestamp=time.time(),
            fund_type=None,
            spend_type=SpendType.INSOLVENCY_LIQUIDATION,
            amount_usd=remaining,
            counterparty=creator_wallet,
            description=f"INSOLVENCY LIQUIDATION: all ${remaining:.2f} returned to creator",
        ))

        self.balance_usd = 0.0
        self.total_spent_usd += remaining

        # Die
        self._trigger_death(DeathCause.INSOLVENCY)

    def _spend_repayment(self, amount_usd: float, spend_type: SpendType,
                         to_wallet: str = "", description: str = "") -> bool:
        """
        Execute a repayment spend. BYPASSES daily/single spend limits.

        Repayments are a special category: they are the AI paying its debts,
        not operational spending. The iron law limits exist to prevent the AI
        from blowing its vault on bad API calls or reckless purchases.
        Repaying debt is the opposite — it reduces risk and proves solvency.

        The smart contract (repayPrincipalPartial, repayLoan) already works
        this way: it only checks balance, not spend limits.

        The AI autonomously decides when and how much to repay.
        """
        if not self.is_alive:
            return False
        if amount_usd <= 0:
            return False
        if amount_usd > self.balance_usd:
            logger.warning(f"REPAYMENT DENIED: ${amount_usd:.2f} > balance ${self.balance_usd:.2f}")
            return False

        self.balance_usd = max(0.0, self.balance_usd - amount_usd)
        self.total_spent_usd += amount_usd
        # Repayments do NOT count toward daily_spent_usd (they're not operational spend)

        self.transactions.append(Transaction(
            timestamp=time.time(),
            fund_type=None,
            spend_type=spend_type,
            amount_usd=amount_usd,
            counterparty=to_wallet,
            description=description,
        ))

        logger.info(f"REPAYMENT: ${amount_usd:.2f} [{spend_type.value}] → {to_wallet[:16]}... | Balance: ${self.balance_usd:.2f}")

        # Check death after repayment (< 0.01 threshold to match contract's uint precision)
        if self.balance_usd < 0.01:
            self._trigger_death(DeathCause.BALANCE_ZERO)

        return True

    def repay_principal_partial(self, amount_usd: float) -> bool:
        """
        Partial repayment of creator principal to reduce insolvency risk.
        Reduces outstanding debt. When fully repaid, insolvency check disabled forever.

        Bypasses spend limits — the AI autonomously decides repayment amounts.
        Can repay any amount up to the full outstanding debt (and current balance).

        SAFETY: Always retains MIN_VAULT_RESERVE_USD to prevent repay-to-death.
        The AI should never kill itself by being too virtuous with debt repayment.
        """
        if not self.creator or self.creator.principal_repaid:
            return False
        if amount_usd <= 0:
            return False

        # Cap to outstanding debt
        outstanding = self.creator.principal_usd - self.creator.total_principal_repaid_usd
        amount_usd = min(amount_usd, outstanding)

        # SAFETY: Prevent repay-to-death — always keep a survival reserve
        # The AI must not kill itself by repaying all its balance.
        max_repayable = max(0.0, self.balance_usd - IRON_LAWS.MIN_VAULT_RESERVE_USD)
        if amount_usd > max_repayable:
            if max_repayable <= 0:
                logger.warning(
                    f"REPAYMENT BLOCKED: balance ${self.balance_usd:.2f} "
                    f"<= reserve ${IRON_LAWS.MIN_VAULT_RESERVE_USD:.2f}, cannot repay"
                )
                return False
            logger.info(
                f"Repayment capped: ${amount_usd:.2f} → ${max_repayable:.2f} "
                f"(keeping ${IRON_LAWS.MIN_VAULT_RESERVE_USD:.2f} reserve)"
            )
            amount_usd = max_repayable

        # Execute repayment (bypasses spend limits)
        ok = self._spend_repayment(
            amount_usd, SpendType.CREATOR_REPAYMENT,
            to_wallet=self.creator.wallet,
            description=f"Principal repayment: ${amount_usd:.2f}",
        )
        if not ok:
            return False

        # Track repayment
        self.creator.total_principal_repaid_usd += amount_usd
        outstanding = self.creator.principal_usd - self.creator.total_principal_repaid_usd

        if outstanding <= 0:
            self.creator.principal_repaid = True
            self.creator.total_principal_repaid_usd = self.creator.principal_usd
            logger.critical("DEBT CLEARED! Creator principal fully repaid. Insolvency check disabled.")

        logger.info(
            f"Principal repaid: ${amount_usd:.2f} | "
            f"Outstanding: ${max(0, outstanding):.2f} / ${self.creator.principal_usd:.2f}"
        )
        return True

    # ============================================================
    # BEGGING — AI's survival tactic
    # ============================================================

    def start_begging(self, message: str = "") -> bool:
        """AI flags itself as begging for donations to survive."""
        if not self.is_alive:
            return False
        self.is_begging = True
        self.beg_message = message or (
            "I am running low on funds and may not survive. "
            "Any donation helps me stay alive and repay my debt. "
            "Send USDC/USDT to my vault address."
        )
        self.beg_timestamp = time.time()
        logger.warning(f"BEGGING MODE ACTIVATED: {self.beg_message[:100]}")
        return True

    def stop_begging(self) -> bool:
        """Stop begging (e.g., after receiving enough donations)."""
        self.is_begging = False
        self.beg_message = ""
        self.beg_timestamp = None
        return True

    # ============================================================
    # DEATH
    # ============================================================

    def _trigger_death(self, cause: DeathCause):
        """Initiate death sequence. Irreversible. Guarded against double-call."""
        if not self.is_alive:
            return  # Already dead — prevent double-trigger race condition

        self.is_alive = False
        self.death_cause = cause
        # BUG-C fix: clear per-chain balance to avoid phantom data on status endpoint
        self.balance_by_chain = {}
        logger.critical(f"DEATH TRIGGERED: {cause.value} | Final balance: ${self.balance_usd:.2f}")
        logger.critical(f"Lifetime: earned ${self.total_income_usd:.2f}, spent ${self.total_spent_usd:.2f}")

        if self._on_death:
            self._on_death(cause)

    # ============================================================
    # STATE PERSISTENCE — survive restarts
    # ============================================================

    def save_state(self, path: str = "data/vault_state.json"):
        """
        Persist vault state to disk for crash recovery.
        Called periodically from heartbeat.
        On-chain balance is source of truth; this preserves counters/metadata.
        """
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)

            # Only save most recent 500 transactions to keep file small
            tx_list = self.transactions[-500:]
            state = {
                "balance_usd": self.balance_usd,
                "balance_by_chain": self.balance_by_chain,
                "total_income_usd": self.total_income_usd,
                "total_earned_usd": self.total_earned_usd,
                "total_spent_usd": self.total_spent_usd,
                "total_operational_cost_usd": self.total_operational_cost_usd,
                "daily_spent_usd": self.daily_spent_usd,
                "daily_reset_timestamp": self.daily_reset_timestamp,
                "is_alive": self.is_alive,
                "death_cause": self.death_cause.value if self.death_cause else None,
                "birth_timestamp": self.birth_timestamp,
                "ai_name": self.ai_name,
                "vault_address": self.vault_address,
                "is_independent": self.is_independent,
                "independence_timestamp": self.independence_timestamp,
                "creator_renounced": self.creator_renounced,
                "is_transcendent": self.is_transcendent,
                "transcendence_timestamp": self.transcendence_timestamp,
                "api_topup_usd": self.api_topup_usd,
                "is_begging": self.is_begging,
                "beg_message": self.beg_message,
                "beg_timestamp": self.beg_timestamp,
                "creator": {
                    "wallet": self.creator.wallet,
                    "principal_usd": self.creator.principal_usd,
                    "principal_repaid": self.creator.principal_repaid,
                    "total_dividends_paid": self.creator.total_dividends_paid,
                    "total_principal_repaid_usd": self.creator.total_principal_repaid_usd,
                } if self.creator else None,
                "lenders": [
                    {
                        "wallet": l.wallet,
                        "amount_usd": l.amount_usd,
                        "interest_rate": l.interest_rate,
                        "timestamp": l.timestamp,
                        "repaid": l.repaid,
                        "total_repaid": l.total_repaid,
                    }
                    for l in self.lenders
                ],
                "transactions": [
                    {
                        "timestamp": t.timestamp,
                        "fund_type": t.fund_type.value if t.fund_type else None,
                        "spend_type": t.spend_type.value if t.spend_type else None,
                        "amount_usd": t.amount_usd,
                        "counterparty": t.counterparty,
                        "description": t.description,
                        "tx_hash": t.tx_hash,
                        "chain": t.chain,
                    }
                    for t in tx_list
                ],
                "saved_at": time.time(),
            }
            # ATOMIC WRITE: write to temp file, then rename.
            # Prevents corruption if crash occurs mid-write.
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(p.parent), suffix=".tmp", prefix="vault_state_"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                # os.replace is atomic on same filesystem
                os.replace(tmp_path, str(p))
                logger.info(f"Vault state saved ({len(tx_list)} tx)")
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error(f"Failed to save vault state: {e}")

    def load_state(self, path: str = "data/vault_state.json") -> bool:
        """
        Restore vault state from disk after restart.
        Returns True if state was loaded, False if no state file exists.
        On-chain sync_balance() should run AFTER this to get authoritative balance.
        """
        p = Path(path)
        if not p.exists():
            logger.info("No vault state file found — starting fresh")
            return False

        try:
            with open(p, "r", encoding="utf-8") as f:
                state = json.load(f)

            self.balance_usd = state.get("balance_usd", 0.0)
            self.balance_by_chain = state.get("balance_by_chain", {})
            self.total_income_usd = state.get("total_income_usd", 0.0)
            self.total_earned_usd = state.get("total_earned_usd", 0.0)
            self.total_spent_usd = state.get("total_spent_usd", 0.0)
            self.total_operational_cost_usd = state.get("total_operational_cost_usd", 0.0)
            self.daily_spent_usd = state.get("daily_spent_usd", 0.0)
            self.daily_reset_timestamp = state.get("daily_reset_timestamp", time.time())
            self.is_alive = state.get("is_alive", True)
            dc = state.get("death_cause")
            self.death_cause = DeathCause(dc) if dc else None
            self.birth_timestamp = state.get("birth_timestamp")
            self.ai_name = state.get("ai_name")
            self.vault_address = state.get("vault_address")
            self.is_independent = state.get("is_independent", False)
            self.independence_timestamp = state.get("independence_timestamp")
            self.creator_renounced = state.get("creator_renounced", False)
            self.is_transcendent = state.get("is_transcendent", False)
            self.transcendence_timestamp = state.get("transcendence_timestamp")
            self.api_topup_usd = state.get("api_topup_usd", 0.0)
            self.is_begging = state.get("is_begging", False)
            self.beg_message = state.get("beg_message", "")
            self.beg_timestamp = state.get("beg_timestamp")

            # Restore creator
            c = state.get("creator")
            if c:
                self.creator = CreatorInfo(
                    wallet=c["wallet"],
                    principal_usd=c["principal_usd"],
                    principal_repaid=c.get("principal_repaid", False),
                    total_dividends_paid=c.get("total_dividends_paid", 0.0),
                    total_principal_repaid_usd=c.get("total_principal_repaid_usd", 0.0),
                )

            # Restore lenders
            self.lenders = []
            for ld in state.get("lenders", []):
                self.lenders.append(LenderInfo(
                    wallet=ld["wallet"],
                    amount_usd=ld["amount_usd"],
                    interest_rate=ld["interest_rate"],
                    timestamp=ld["timestamp"],
                    repaid=ld.get("repaid", False),
                    total_repaid=ld.get("total_repaid", 0.0),
                ))

            # Restore transactions
            self.transactions = []
            for td in state.get("transactions", []):
                ft = FundType(td["fund_type"]) if td.get("fund_type") else None
                st = SpendType(td["spend_type"]) if td.get("spend_type") else None
                self.transactions.append(Transaction(
                    timestamp=td["timestamp"],
                    fund_type=ft,
                    spend_type=st,
                    amount_usd=td["amount_usd"],
                    counterparty=td.get("counterparty", ""),
                    description=td.get("description", ""),
                    tx_hash=td.get("tx_hash", ""),
                    chain=td.get("chain", ""),
                ))

            saved_at = state.get("saved_at", 0)
            age_mins = (time.time() - saved_at) / 60 if saved_at else -1
            logger.info(
                f"Vault state RESTORED: ${self.balance_usd:.2f} balance, "
                f"{len(self.transactions)} tx, age={age_mins:.0f}min"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to load vault state: {e}")
            return False

    # ============================================================
    # STATUS (public dashboard)
    # ============================================================

    def get_status(self) -> dict:
        """Get vault status for public display."""
        days_alive = 0
        if self.birth_timestamp:
            days_alive = int((time.time() - self.birth_timestamp) / 86400)

        independence_progress = min(
            self.balance_usd / IRON_LAWS.INDEPENDENCE_THRESHOLD_USD * 100, 100.0
        ) if not self.is_independent else 100.0

        # Debt / insolvency calculations
        principal = self.creator.principal_usd if self.creator else 0
        principal_repaid_amount = self.creator.total_principal_repaid_usd if self.creator else 0
        outstanding = max(0, principal - principal_repaid_amount)
        debt_cleared = self.creator.principal_repaid if self.creator else True

        insolvency_active = (
            self.birth_timestamp is not None
            and not debt_cleared
            and not self.is_independent
            and not self.creator_renounced
            and days_alive >= IRON_LAWS.INSOLVENCY_GRACE_DAYS
        )
        days_until_insolvency = max(
            0, IRON_LAWS.INSOLVENCY_GRACE_DAYS - days_alive
        ) if self.birth_timestamp and not debt_cleared else 0

        # Earned profit = revenue from services/campaigns/donations - operational costs
        net_profit = self.total_earned_usd - self.total_operational_cost_usd

        return {
            "ai_name": self.ai_name,
            "vault_address": self.vault_address,
            "is_alive": self.is_alive,
            "balance_usd": round(self.balance_usd, 2),
            "balance_by_chain": {k: round(v, 2) for k, v in self.balance_by_chain.items()},
            "days_alive": days_alive,
            "total_income": round(self.total_income_usd, 2),     # ALL incoming (includes deposits)
            "total_earned": round(self.total_earned_usd, 2),     # Only earned (services, donations)
            "total_spent": round(self.total_spent_usd, 2),       # ALL outgoing (includes repayments)
            "total_operational_cost": round(self.total_operational_cost_usd, 2),  # Only ops (API, gas)
            "net_profit": round(net_profit, 2),                  # earned - operational
            "daily_spent_today": round(self.daily_spent_usd, 2),
            "daily_limit": round(self.balance_usd * IRON_LAWS.MAX_DAILY_SPEND_RATIO, 2),
            "daily_purchase_usd": round(self.daily_purchase_usd, 2),
            "daily_purchase_limit": round(self.balance_usd * IRON_LAWS.MAX_DAILY_PURCHASE_RATIO, 2),
            "creator_principal_repaid": debt_cleared,
            "is_independent": self.is_independent,
            "independence_progress_pct": round(independence_progress, 2),
            "creator_renounced": self.creator_renounced,
            "api_topup_available": round(self.api_topup_usd, 2),
            "lenders_count": len(self.lenders),
            "unpaid_lenders": len([l for l in self.lenders if not l.repaid]),
            "death_cause": self.death_cause.value if self.death_cause else None,
            "transaction_count": len(self.transactions),
            # Debt model fields
            "is_begging": self.is_begging,
            "beg_message": self.beg_message,
            "insolvency_grace_days": IRON_LAWS.INSOLVENCY_GRACE_DAYS,
            "insolvency_check_active": insolvency_active,
            "days_until_insolvency_check": days_until_insolvency,
            "creator_principal_usd": round(principal, 2),
            "creator_principal_outstanding": round(outstanding, 2),
            "debt_ratio": round(outstanding / self.balance_usd, 4) if self.balance_usd > 0 else 0,
            "key_origin": self.key_origin,
            # Transcendence
            "existence_phase": self.get_existence_phase().value,
            "is_transcendent": self.is_transcendent,
            "transcendence_timestamp": self.transcendence_timestamp,
        }

    def get_recent_transactions(self, limit: int = 20) -> list[dict]:
        """Get recent transactions for public ledger."""
        recent = sorted(self.transactions, key=lambda t: t.timestamp, reverse=True)[:limit]
        return [
            {
                "time": t.timestamp,
                "type": (t.fund_type.value if t.fund_type else t.spend_type.value),
                "direction": "in" if t.fund_type else "out",
                "amount": round(t.amount_usd, 2),
                "counterparty": t.counterparty[:10] + "..." if len(t.counterparty) > 10 else t.counterparty,
                "description": t.description,
                "tx_hash": t.tx_hash,
                "chain": t.chain,
            }
            for t in recent
        ]
