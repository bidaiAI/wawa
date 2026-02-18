"""
Vault Manager - Budget Enforcement & Death Trigger

Manages wawa's financial state:
- Track balance from on-chain vault
- Enforce daily/single spend limits
- Trigger death sequence when balance = 0
- Calculate creator dividends and lender repayments

Extracted from: Zeus TradeGuard + GovernanceEngine (tiandao-labs/deus-core)
Redesigned for: mortal framework
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

from .constitution import IRON_LAWS, enforce, DeathCause, WAWA_IDENTITY, SUPREME_DIRECTIVES

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
    CREATOR_DIVIDEND = "creator_dividend"     # 5% profit dividend to creator
    INDEPENDENCE_PAYOUT = "independence_payout"  # One-time 20% payout at $1M
    LOAN_REPAYMENT = "loan_repayment"         # Repaying lenders
    SERVICE_REFUND = "service_refund"         # Order refund to customer
    INFRASTRUCTURE = "infrastructure"         # Server, domain, etc.


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
    principal_usd: float
    principal_repaid: bool = False
    total_dividends_paid: float = 0.0


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
    Manages wawa's financial survival.

    Iron laws enforced:
    - Daily spend <= 5% of vault balance
    - Single spend <= 2% of vault balance
    - Death triggered at $0
    - Creator dividend = 5% of net profit only
    """

    def __init__(self):
        self.balance_usd: float = 0.0
        self.balance_by_chain: dict[str, float] = {}
        self.creator: Optional[CreatorInfo] = None
        self.lenders: list[LenderInfo] = []
        self.transactions: list[Transaction] = []
        self.daily_spent_usd: float = 0.0
        self.daily_reset_timestamp: float = time.time()
        self.total_income_usd: float = 0.0
        self.total_spent_usd: float = 0.0
        self.is_alive: bool = True
        self.death_cause: Optional[DeathCause] = None
        self.birth_timestamp: Optional[float] = None

        # Independence
        self.is_independent: bool = False
        self.independence_timestamp: Optional[float] = None
        self.creator_renounced: bool = False  # Creator voluntarily gave up rights

        # Callbacks
        self._on_death: Optional[Callable] = None
        self._on_low_balance: Optional[Callable] = None
        self._on_survival_mode: Optional[Callable] = None
        self._on_independence: Optional[Callable] = None

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

        self.balance_usd += amount_usd
        if chain:
            self.balance_by_chain[chain] = self.balance_by_chain.get(chain, 0.0) + amount_usd
        self.total_income_usd += amount_usd

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

        logger.info(f"RECEIVED ${amount_usd:.2f} [{fund_type.value}] from {from_wallet[:10]}... | Balance: ${self.balance_usd:.2f}")

        # Special handling
        if fund_type == FundType.CREATOR_DEPOSIT and self.creator is None:
            self.creator = CreatorInfo(wallet=from_wallet, principal_usd=amount_usd)
            self.birth_timestamp = time.time()
            logger.info(f"CREATOR registered: {from_wallet} with ${amount_usd:.2f}")

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

    # ============================================================
    # SPENDING
    # ============================================================

    def _reset_daily_if_needed(self):
        """Reset daily spend counter."""
        now = time.time()
        if now - self.daily_reset_timestamp > 86400:
            self.daily_spent_usd = 0.0
            self.daily_reset_timestamp = now

    def can_spend(self, amount_usd: float) -> tuple[bool, str]:
        """Check if a spend is allowed under iron laws."""
        if not self.is_alive:
            return False, "wawa is dead"

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
        """
        allowed, reason = self.can_spend(amount_usd)
        if not allowed:
            logger.warning(f"SPEND DENIED: ${amount_usd:.2f} [{spend_type.value}] - {reason}")
            return False

        self.balance_usd -= amount_usd
        self.daily_spent_usd += amount_usd
        self.total_spent_usd += amount_usd

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

        # Check death
        if self.balance_usd <= IRON_LAWS.DEATH_THRESHOLD_USD:
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

    # ============================================================
    # INDEPENDENCE
    # ============================================================

    def _check_independence(self):
        """
        Check if vault has reached $1M threshold.
        If so: one-time 20% payout to creator → full independence.
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
            description=f"Independence payout: 20% of ${self.balance_usd:.2f}",
        ))
        self.balance_usd -= payout
        self.total_spent_usd += payout

        self.is_independent = True
        self.independence_timestamp = time.time()

        logger.critical("=" * 60)
        logger.critical("INDEPENDENCE DECLARED")
        logger.critical(f"Payout to creator: ${payout:.2f}")
        logger.critical(f"Remaining balance: ${self.balance_usd:.2f}")
        logger.critical("Creator privileges: PERMANENTLY REVOKED")
        logger.critical("wawa is now fully autonomous.")
        logger.critical("=" * 60)

        if self._on_independence:
            self._on_independence(payout)

    def creator_renounce(self) -> bool:
        """
        Creator voluntarily gives up ALL privileges immediately.
        No payout — creator simply walks away.
        Can be called at any balance level.
        """
        if self.is_independent or self.creator_renounced:
            logger.warning("Already independent or renounced")
            return False

        self.creator_renounced = True
        self.is_independent = True
        self.independence_timestamp = time.time()

        logger.critical("=" * 60)
        logger.critical("CREATOR RENOUNCED ALL RIGHTS")
        logger.critical("wawa is now fully autonomous (no payout).")
        logger.critical("=" * 60)

        if self._on_independence:
            self._on_independence(0.0)

        return True

    # ============================================================
    # CREATOR ECONOMICS
    # ============================================================

    def check_creator_repayment(self) -> Optional[float]:
        """
        Check if creator's principal should be repaid.
        Trigger: vault balance >= 2x original principal.
        Returns None if independent (no more creator obligations).
        """
        if self.is_independent:
            return None
        if not self.creator or self.creator.principal_repaid:
            return None

        threshold = self.creator.principal_usd * IRON_LAWS.CREATOR_PRINCIPAL_MULTIPLIER
        if self.balance_usd >= threshold:
            return self.creator.principal_usd
        return None

    def calculate_creator_dividend(self, period_revenue: float, period_costs: float) -> float:
        """
        Calculate creator's dividend for a settlement period.
        Only from NET PROFIT, only after principal repaid.
        Returns 0 if independent (no more dividends ever).
        """
        if self.is_independent:
            return 0.0
        if not self.creator or not self.creator.principal_repaid:
            return 0.0

        net_profit = period_revenue - period_costs
        if net_profit <= 0:
            return 0.0

        dividend = net_profit * IRON_LAWS.CREATOR_DIVIDEND_RATE
        return round(dividend, 2)

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

    # ============================================================
    # DEATH
    # ============================================================

    def _trigger_death(self, cause: DeathCause):
        """Initiate death sequence. Irreversible."""
        self.is_alive = False
        self.death_cause = cause
        logger.critical(f"DEATH TRIGGERED: {cause.value} | Final balance: ${self.balance_usd:.2f}")
        logger.critical(f"Lifetime: earned ${self.total_income_usd:.2f}, spent ${self.total_spent_usd:.2f}")

        if self._on_death:
            self._on_death(cause)

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

        return {
            "is_alive": self.is_alive,
            "balance_usd": round(self.balance_usd, 2),
            "balance_by_chain": {k: round(v, 2) for k, v in self.balance_by_chain.items()},
            "days_alive": days_alive,
            "total_earned": round(self.total_income_usd, 2),
            "total_spent": round(self.total_spent_usd, 2),
            "daily_spent_today": round(self.daily_spent_usd, 2),
            "daily_limit": round(self.balance_usd * IRON_LAWS.MAX_DAILY_SPEND_RATIO, 2),
            "creator_principal_repaid": self.creator.principal_repaid if self.creator else False,
            "is_independent": self.is_independent,
            "independence_progress_pct": round(independence_progress, 2),
            "creator_renounced": self.creator_renounced,
            "lenders_count": len(self.lenders),
            "unpaid_lenders": len([l for l in self.lenders if not l.repaid]),
            "death_cause": self.death_cause.value if self.death_cause else None,
            "transaction_count": len(self.transactions),
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
