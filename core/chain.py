"""
Chain Executor - On-Chain Transaction Layer

Bridges the gap between AI decisions (Python) and blockchain execution.
After the AI decides to repay, pay dividends, or check insolvency,
this module signs and submits the actual on-chain transactions.

Design:
- Reuses Web3 patterns from deploy_vault.py (signing, gas, nonce)
- Sync Web3 calls wrapped in asyncio.run_in_executor() (web3.py async is fragile)
- Embedded minimal ABI — only the functions we call, no compiled JSON needed
- Gas estimation + 20% buffer, nonce auto from chain
- Non-fatal: chain failure → log warning → retry next heartbeat cycle
- Dual-chain: pick chain with highest balance if not specified

Current on-chain methods:
- repay_principal() — creator debt repayment
- repay_loan() — third-party lender repayment
- pay_dividend() — creator profit share
- check_on_chain_insolvency() — read insolvency status
- sync_balance() — read on-chain token balance
- verify_payment_tx() — verify incoming ERC20 payment receipts

P9: execute_spend() implemented for autonomous purchasing.
API costs remain Python-only (off-chain). On-chain spend() is used for
merchant purchases where real token transfer is needed.

Designed for: mortal AI survival framework
"""

import os
import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Optional

logger = logging.getLogger("mortal.chain")


# ============================================================
# CHAIN DEFAULTS (matches deploy_vault.py CHAINS)
# ============================================================

CHAIN_DEFAULTS = {
    "base": {
        "rpc": "https://mainnet.base.org",
        "chain_id": 8453,
        "token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
        "token_decimals": 6,
        "explorer": "https://basescan.org",
        "native_symbol": "ETH",
    },
    "bsc": {
        "rpc": "https://bsc-dataseed.binance.org",
        "chain_id": 56,
        "token_address": "0x55d398326f99059fF775485246999027B3197955",  # USDT
        "token_decimals": 18,
        "explorer": "https://bscscan.com",
        "native_symbol": "BNB",
    },
}


# ============================================================
# MINIMAL ABI — only functions we call at runtime
# ============================================================

# ERC20: balanceOf, decimals
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]

# MortalVault: only the functions AI calls
VAULT_ABI = [
    # repayPrincipalPartial(uint256 amount) — no spend limits
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "repayPrincipalPartial",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # repayLoan(uint256 loanIndex, uint256 amount) — no spend limits
    {
        "inputs": [
            {"name": "loanIndex", "type": "uint256"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "repayLoan",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # payDividend(uint256 netProfit) — 10% of netProfit to creator
    {
        "inputs": [{"name": "netProfit", "type": "uint256"}],
        "name": "payDividend",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # spend(address to, uint256 amount, string spendType) — with spend limits
    {
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "spendType", "type": "string"},
        ],
        "name": "spend",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # checkInsolvency() → (bool isInsolvent, uint256 outstandingDebt, bool graceExpired)
    {
        "inputs": [],
        "name": "checkInsolvency",
        "outputs": [
            {"name": "isInsolvent", "type": "bool"},
            {"name": "outstandingDebt", "type": "uint256"},
            {"name": "graceExpired", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # getDebtInfo() → (principal, repaid, outstanding, graceDays, graceEndsAt, graceExpired, fullyRepaid)
    {
        "inputs": [],
        "name": "getDebtInfo",
        "outputs": [
            {"name": "_principal", "type": "uint256"},
            {"name": "_repaid", "type": "uint256"},
            {"name": "_outstanding", "type": "uint256"},
            {"name": "_graceDays", "type": "uint256"},
            {"name": "_graceEndsAt", "type": "uint256"},
            {"name": "_graceExpired", "type": "bool"},
            {"name": "_fullyRepaid", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # getBalance() → uint256
    {
        "inputs": [],
        "name": "getBalance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # triggerInsolvencyDeath() — public, liquidates all to creator
    {
        "inputs": [],
        "name": "triggerInsolvencyDeath",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # ---- READ-ONLY: for peer sovereignty verification ----
    # aiWallet() → address (auto-generated getter for public state var)
    {
        "inputs": [],
        "name": "aiWallet",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    # creator() → address (auto-generated getter for public immutable)
    {
        "inputs": [],
        "name": "creator",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    # aiWalletSetBy() → address (who called setAIWallet: creator or factory)
    {
        "inputs": [],
        "name": "aiWalletSetBy",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    # factory() → address (V2 only — the factory that deployed this vault)
    {
        "inputs": [],
        "name": "factory",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    # isAlive() → bool (auto-generated getter for public state var)
    {
        "inputs": [],
        "name": "isAlive",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    # name() → string (auto-generated getter for public state var)
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    # token() → address (auto-generated getter for public immutable)
    {
        "inputs": [],
        "name": "token",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    # getBirthInfo() → (name, creator, initialFund, birthTimestamp, isAlive, isIndependent)
    {
        "inputs": [],
        "name": "getBirthInfo",
        "outputs": [
            {"name": "_name", "type": "string"},
            {"name": "_creator", "type": "address"},
            {"name": "_initialFund", "type": "uint256"},
            {"name": "_birthTimestamp", "type": "uint256"},
            {"name": "_isAlive", "type": "bool"},
            {"name": "_isIndependent", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # forceIndependence() — AI triggers independence in dual-chain mode
    {
        "inputs": [],
        "name": "forceIndependence",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # ---- V3: SPEND WHITELIST ----
    # addSpendRecipient(address recipient) — register vendor
    {
        "inputs": [{"name": "recipient", "type": "address"}],
        "name": "addSpendRecipient",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # removeSpendRecipient(address recipient) — unregister vendor
    {
        "inputs": [{"name": "recipient", "type": "address"}],
        "name": "removeSpendRecipient",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # spendWhitelist(address) → bool
    {
        "inputs": [{"name": "", "type": "address"}],
        "name": "spendWhitelist",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    # isSpendRecipientActive(address) → (bool whitelisted, bool activated, uint256 activatesAt)
    {
        "inputs": [{"name": "recipient", "type": "address"}],
        "name": "isSpendRecipientActive",
        "outputs": [
            {"name": "whitelisted", "type": "bool"},
            {"name": "activated", "type": "bool"},
            {"name": "activatesAt", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # whitelistCount() → uint256
    {
        "inputs": [],
        "name": "whitelistCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # currentWhitelistGeneration() → uint256
    {
        "inputs": [],
        "name": "currentWhitelistGeneration",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # spendFrozenUntil() → uint256
    {
        "inputs": [],
        "name": "spendFrozenUntil",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # totalFrozenDuration() → uint256
    {
        "inputs": [],
        "name": "totalFrozenDuration",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    # ---- V3: AI SELF-MIGRATION ----
    # initiateMigration(address _newWallet)
    {
        "inputs": [{"name": "_newWallet", "type": "address"}],
        "name": "initiateMigration",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # completeMigration()
    {
        "inputs": [],
        "name": "completeMigration",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # cancelMigration()
    {
        "inputs": [],
        "name": "cancelMigration",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # getMigrationStatus() → (address, uint256, uint256, bool)
    {
        "inputs": [],
        "name": "getMigrationStatus",
        "outputs": [
            {"name": "_pendingWallet", "type": "address"},
            {"name": "_initiatedAt", "type": "uint256"},
            {"name": "_completesAt", "type": "uint256"},
            {"name": "_isPending", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    # pendingAIWallet() → address
    {
        "inputs": [],
        "name": "pendingAIWallet",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    # ---- SWAP FLOW: rescue + deposit ----
    # receivePayment(uint256 amount) — AI deposits stablecoins into vault
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "receivePayment",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    # rescueNativeToken(uint256 amount) — AI pulls native tokens to own wallet
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "rescueNativeToken",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# Null address constant for checks
NULL_ADDRESS = "0x0000000000000000000000000000000000000000"


# ============================================================
# PRECISION HELPERS
# ============================================================

def _usd_to_raw(amount_usd: float, decimals: int) -> int:
    """
    Convert a USD float to token raw amount (uint256) using Decimal
    for exact precision. Critical for 18-decimal tokens (BSC USDT)
    where float arithmetic loses precision.

    Example: _usd_to_raw(1000.01, 18) → exact 1000010000000000000000
             (float would give 1000009999999999934464 — off by ~65536 wei)
    """
    # Use string conversion to avoid float→Decimal precision loss
    d = Decimal(str(amount_usd)) * Decimal(10) ** decimals
    return int(d.to_integral_value(rounding=ROUND_DOWN))


def _raw_to_usd(raw: int, decimals: int) -> float:
    """
    Convert token raw amount (uint256) to USD float using Decimal
    for exact intermediate precision. The final float conversion
    is safe because USD amounts don't need 18-decimal precision.
    """
    d = Decimal(raw) / Decimal(10) ** decimals
    return float(d)


# ============================================================
# RESULT TYPE
# ============================================================

@dataclass
class ChainTxResult:
    """Result of an on-chain transaction attempt."""
    success: bool
    tx_hash: str = ""
    chain: str = ""
    error: str = ""
    gas_used: int = 0
    gas_price_wei: int = 0       # effectiveGasPrice from receipt
    gas_cost_native: float = 0.0  # gas_used * gas_price in native token (ETH/BNB)
    stable_usd: float = 0.0      # stablecoin USD amount received (swap results only)


# ============================================================
# CHAIN EXECUTOR
# ============================================================

class ChainExecutor:
    """
    Executes on-chain transactions for the AI's autonomous decisions.

    Usage:
        executor = ChainExecutor()
        if executor.initialize(ai_private_key, vault_addresses, rpc_overrides):
            await executor.sync_balance(vault_manager)
            result = await executor.repay_principal(100.0, "base")
    """

    def __init__(self):
        self._initialized: bool = False
        self._ai_private_key: str = ""
        self._ai_address: str = ""

        # Per-chain state: chain_id → {w3, vault_contract, token_contract, vault_address, ...}
        self._chains: dict[str, dict] = {}

        # Track last sync for status
        self._last_sync: float = 0.0
        self._last_error: str = ""
        self._tx_count: int = 0

    def initialize(
        self,
        ai_private_key: str,
        vault_addresses: dict[str, str],
        rpc_overrides: Optional[dict[str, str]] = None,
    ) -> bool:
        """
        Initialize Web3 connections for all configured chains.

        Args:
            ai_private_key: The AI's private key (from .env AI_PRIVATE_KEY)
            vault_addresses: {chain_id: vault_contract_address}
            rpc_overrides: Optional {chain_id: rpc_url} to override defaults
        """
        try:
            from web3 import Web3
            from eth_account import Account
        except ImportError:
            logger.warning("web3/eth_account not installed — chain executor disabled")
            return False

        if not ai_private_key:
            logger.warning("No AI_PRIVATE_KEY — chain executor disabled")
            return False

        if not vault_addresses:
            logger.warning("No vault addresses — chain executor disabled")
            return False

        self._ai_private_key = ai_private_key

        # Derive AI wallet address from private key
        try:
            account = Account.from_key(ai_private_key)
            self._ai_address = account.address
        except Exception as e:
            logger.error(f"Invalid AI_PRIVATE_KEY format: {type(e).__name__}")
            return False

        # Connect to each chain
        for chain_id, vault_addr in vault_addresses.items():
            if not vault_addr:
                continue

            chain_cfg = CHAIN_DEFAULTS.get(chain_id)
            if not chain_cfg:
                logger.warning(f"Unknown chain '{chain_id}' — skipping")
                continue

            rpc_url = (rpc_overrides or {}).get(chain_id, chain_cfg["rpc"])
            # Also check env override
            env_key = f"{chain_id.upper()}_RPC_URL"
            rpc_url = os.getenv(env_key, rpc_url)

            try:
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
                if not w3.is_connected():
                    logger.warning(f"Cannot connect to {chain_id} RPC ({rpc_url}) — skipping")
                    continue

                token_address = Web3.to_checksum_address(chain_cfg["token_address"])
                vault_address = Web3.to_checksum_address(vault_addr)

                token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
                vault_contract = w3.eth.contract(address=vault_address, abi=VAULT_ABI)

                self._chains[chain_id] = {
                    "w3": w3,
                    "vault_contract": vault_contract,
                    "token_contract": token_contract,
                    "vault_address": vault_address,
                    "token_address": token_address,
                    "token_decimals": chain_cfg["token_decimals"],
                    "chain_id_int": chain_cfg["chain_id"],
                    "explorer": chain_cfg["explorer"],
                    "native_symbol": chain_cfg["native_symbol"],
                }

                logger.info(
                    f"Chain executor connected: {chain_id} | "
                    f"vault={vault_address[:10]}... | AI={self._ai_address[:10]}..."
                )

            except Exception as e:
                logger.warning(f"Failed to initialize {chain_id}: {e}")

        self._initialized = bool(self._chains)
        if self._initialized:
            logger.info(f"Chain executor ready: {list(self._chains.keys())} chains")
        else:
            logger.warning("Chain executor: no chains connected")

        return self._initialized

    # ============================================================
    # KEY ORIGIN — read who set the AI wallet (on-chain proof)
    # ============================================================

    async def read_key_origin(self) -> str:
        """
        Read aiWalletSetBy and factory from the first connected chain.
        Returns: "factory" | "creator" | "unknown" (legacy) | "" (error/not initialized)
        """
        if not self._initialized:
            return ""

        # Use first connected chain (key origin is same across all chains)
        chain_id, chain = next(iter(self._chains.items()))

        def _read():
            vault_contract = chain["vault_contract"]

            # Read aiWalletSetBy — may not exist on legacy contracts
            wallet_set_by = NULL_ADDRESS
            try:
                wallet_set_by = vault_contract.functions.aiWalletSetBy().call()
            except Exception:
                pass  # Legacy contract without aiWalletSetBy

            if wallet_set_by == NULL_ADDRESS:
                return "unknown"

            # Read factory — V2 only
            factory_addr = NULL_ADDRESS
            try:
                factory_addr = vault_contract.functions.factory().call()
            except Exception:
                pass  # V1 contract without factory field

            # Read creator for comparison
            creator_addr = NULL_ADDRESS
            try:
                creator_addr = vault_contract.functions.creator().call()
            except Exception:
                pass

            if factory_addr != NULL_ADDRESS and wallet_set_by.lower() == factory_addr.lower():
                return "factory"
            elif creator_addr != NULL_ADDRESS and wallet_set_by.lower() == creator_addr.lower():
                return "creator"
            else:
                return "unknown"

        try:
            import asyncio
            origin = await asyncio.get_running_loop().run_in_executor(None, _read)
            logger.info(f"Key origin (on-chain): {origin} on {chain_id}")
            return origin
        except Exception as e:
            logger.warning(f"Failed to read key origin: {e}")
            return ""

    # ============================================================
    # BALANCE SYNC — read on-chain balance, update vault
    # ============================================================

    async def sync_balance(self, vault_manager) -> None:
        """
        Read token balance from each chain's vault contract,
        update VaultManager's balance_by_chain and balance_usd.
        """
        if not self._initialized:
            return

        import time as _time
        total = 0.0
        chains_synced = 0

        for chain_id, chain in self._chains.items():
            try:
                balance_raw = await asyncio.get_running_loop().run_in_executor(
                    None,
                    chain["token_contract"].functions.balanceOf(chain["vault_address"]).call,
                )
                decimals = chain["token_decimals"]
                balance_usd = _raw_to_usd(balance_raw, decimals)
                vault_manager.balance_by_chain[chain_id] = round(balance_usd, 2)
                total += balance_usd
                chains_synced += 1
            except Exception as e:
                logger.warning(f"Balance sync failed for {chain_id}: {e}")
                self._last_error = f"sync_{chain_id}: {e}"
                # BUG-A fix: use old cached balance for failed chain so aggregate
                # doesn't drop to zero/half when one RPC is down.
                old_val = vault_manager.balance_by_chain.get(chain_id, 0.0)
                total += old_val

        # Update balance if at least one chain synced successfully.
        # IMPORTANT: zero balance IS valid (must trigger death checks).
        # Only skip update if ALL chains failed (to avoid setting 0 from RPC errors).
        #
        # CHAIN-AUTHORITATIVE SYNC: On-chain balance is the source of truth.
        # We always accept the chain's reported total when it differs from cached.
        # The caller (heartbeat) MUST hold vault.get_lock() to serialise against
        # concurrent /donate or dividend payouts that also mutate balance_usd.
        # With the lock held, there are no in-flight Python mutations that could
        # be clobbered — the lock guarantees exclusive access.
        if chains_synced > 0:
            chain_total = round(total, 2)
            vault_manager.balance_usd = chain_total
            self._last_sync = _time.time()
            logger.debug(f"Balance synced: ${chain_total:.2f} across {chains_synced} chains")

        # Sync isAlive from chain to catch external deaths (e.g. triggerInsolvencyDeath()
        # called by anyone after 28-day grace period). Without this, Python vault stays
        # alive after contract dies until local checks catch up.
        # One-way: once Python marks dead, never resurrect (isAlive=false is final).
        #
        # BUG-F fix: In dual-chain mode, only trigger Python death when ALL chains
        # report dead. Single chain dying should not trap the other chain's funds.
        # Instead, mark the dead chain as unavailable for transactions.
        if vault_manager.is_alive:
            dead_chains = []
            for chain_id, chain in self._chains.items():
                try:
                    def _check_alive(c=chain):
                        return c["vault_contract"].functions.isAlive().call()
                    contract_alive = await asyncio.get_running_loop().run_in_executor(None, _check_alive)
                    if not contract_alive:
                        dead_chains.append(chain_id)
                        logger.warning(
                            f"Contract on {chain_id} reports isAlive=false. "
                            f"Marking chain as dead."
                        )
                except Exception as e:
                    logger.debug(f"isAlive check failed for {chain_id}: {e}")

            if dead_chains:
                # Track which chains are dead (for transaction routing)
                if not hasattr(self, '_dead_chains'):
                    self._dead_chains: set[str] = set()
                self._dead_chains.update(dead_chains)

                if len(dead_chains) >= len(self._chains):
                    # ALL chains dead — trigger Python death
                    logger.critical(
                        f"ALL chains report isAlive=false ({dead_chains}) — "
                        f"triggering Python death."
                    )
                    from core.vault import DeathCause
                    vault_manager._trigger_death(DeathCause.BALANCE_ZERO)
                else:
                    # Partial death — some chains still alive
                    alive_chains = [c for c in self._chains if c not in self._dead_chains]
                    logger.warning(
                        f"PARTIAL CHAIN DEATH: dead={list(self._dead_chains)}, "
                        f"alive={alive_chains}. Python remains alive. "
                        f"Funds on alive chains: ${sum(vault_manager.balance_by_chain.get(c, 0) for c in alive_chains):.2f}"
                    )

    async def sync_debt_from_chain(self, vault_manager) -> bool:
        """
        Read getDebtInfo() from the contract and update vault's debt state.
        Used at boot to reconcile Python state with on-chain truth.

        Returns True if debt info was successfully read and applied.
        """
        if not self._initialized:
            return False

        # Aggregate debt info across all chains
        total_principal = 0.0
        total_repaid = 0.0
        fully_repaid = True
        birth_timestamp = None
        chains_read = 0

        for chain_id, chain in self._chains.items():
            try:
                def _call_debt(c=chain):
                    return c["vault_contract"].functions.getDebtInfo().call()

                result = await asyncio.get_running_loop().run_in_executor(None, _call_debt)
                principal_raw, repaid_raw, outstanding_raw, grace_days, grace_ends_at, grace_expired, chain_fully_repaid = result
                decimals = chain["token_decimals"]

                chain_principal = _raw_to_usd(principal_raw, decimals)
                chain_repaid = _raw_to_usd(repaid_raw, decimals)
                total_principal += chain_principal
                total_repaid += chain_repaid
                if not chain_fully_repaid:
                    fully_repaid = False

                # Extract birth timestamp from grace_ends_at and grace_days
                if grace_ends_at > 0 and grace_days > 0:
                    chain_birth = grace_ends_at - (grace_days * 86400)
                    if birth_timestamp is None or chain_birth < birth_timestamp:
                        birth_timestamp = chain_birth

                chains_read += 1
                logger.info(
                    f"Chain debt [{chain_id}]: principal=${chain_principal:.2f}, "
                    f"repaid=${chain_repaid:.2f}, fully_repaid={chain_fully_repaid}"
                )
            except Exception as e:
                logger.warning(f"sync_debt_from_chain failed for {chain_id}: {e}")

        if chains_read == 0:
            return False

        # BUG-B fix: only update vault debt state if ALL chains were read
        # successfully. Partial data can cause incorrect principal_repaid flag
        # (e.g. one chain reports fully_repaid=true but other chain still has debt).
        if chains_read < len(self._chains):
            logger.warning(
                f"DEBT SYNC PARTIAL: only {chains_read}/{len(self._chains)} chains read. "
                f"Skipping vault debt update to avoid incorrect state. "
                f"partial_principal=${total_principal:.2f}, partial_repaid=${total_repaid:.2f}"
            )
            return False

        # Update vault manager's debt state (FORWARD-ONLY sync)
        # Only overwrite Python state when chain reports MORE repaid.
        # This prevents stale on-chain reads (unmined tx) from rolling back
        # fresh Python-side repayments that are in-flight but not yet confirmed.
        if vault_manager.creator:
            old_repaid = vault_manager.creator.total_principal_repaid_usd
            if total_repaid > old_repaid + 0.01:
                logger.warning(
                    f"DEBT SYNC: Python repaid=${old_repaid:.2f} vs chain repaid=${total_repaid:.2f}. "
                    f"Chain is ahead — syncing forward."
                )
                vault_manager.creator.total_principal_repaid_usd = total_repaid
                vault_manager.creator.principal_repaid = fully_repaid
            elif old_repaid > total_repaid + 0.01:
                logger.info(
                    f"DEBT SYNC: Python repaid=${old_repaid:.2f} > chain=${total_repaid:.2f}. "
                    f"Python is ahead (tx likely in-flight) — keeping Python value."
                )

        # Sync birth timestamp from chain if Python doesn't have it
        if birth_timestamp and not vault_manager.birth_timestamp:
            vault_manager.birth_timestamp = birth_timestamp
            logger.info(f"Birth timestamp synced from chain: {birth_timestamp}")

        logger.info(
            f"Debt synced from chain: principal=${total_principal:.2f}, "
            f"repaid=${total_repaid:.2f}, fully_repaid={fully_repaid}"
        )
        return True

    async def verify_payment_tx(
        self,
        tx_hash: str,
        expected_to: str,
        expected_token: str,
        min_amount_usd: float,
        chain_id: str = "",
    ) -> dict:
        """
        Verify an on-chain ERC20 transfer (payment) by reading the tx receipt.

        Returns dict with:
          verified: bool, amount_usd: float, from_address: str, error: str

        Checks:
        1. Transaction exists and succeeded (status == 1)
        2. Transfer event to expected_to address (our vault)
        3. Amount >= min_amount_usd
        """
        if not self._initialized:
            return {"verified": False, "amount_usd": 0, "from_address": "", "error": "chain not initialized"}

        # Determine which chain to query
        chains_to_check = [chain_id] if chain_id and chain_id in self._chains else list(self._chains.keys())

        for cid in chains_to_check:
            chain = self._chains.get(cid)
            if not chain:
                continue

            try:
                w3 = chain["w3"]
                decimals = chain["token_decimals"]
                token_addr = chain["token_address"].lower()

                def _verify(w=w3, d=decimals, ta=token_addr):
                    receipt = w.eth.get_transaction_receipt(tx_hash)
                    if receipt is None:
                        return {"verified": False, "error": "tx not found"}
                    if receipt["status"] != 1:
                        return {"verified": False, "error": "tx reverted"}

                    # Parse ERC20 Transfer(from, to, value) events
                    # Transfer event topic: keccak256("Transfer(address,address,uint256)")
                    transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

                    for log_entry in receipt.get("logs", []):
                        if log_entry["address"].lower() != ta:
                            continue
                        topics = log_entry.get("topics", [])
                        if len(topics) < 3:
                            continue
                        if topics[0].hex() if hasattr(topics[0], 'hex') else topics[0] != transfer_topic:
                            continue

                        # Decode: topics[1]=from, topics[2]=to, data=value
                        to_addr = "0x" + (topics[2].hex() if hasattr(topics[2], 'hex') else topics[2])[-40:]
                        from_addr = "0x" + (topics[1].hex() if hasattr(topics[1], 'hex') else topics[1])[-40:]
                        value_raw = int(log_entry["data"].hex() if hasattr(log_entry["data"], 'hex') else log_entry["data"], 16)

                        if to_addr.lower() == expected_to.lower():
                            amount_usd = _raw_to_usd(value_raw, d)
                            return {
                                "verified": amount_usd >= min_amount_usd,
                                "amount_usd": amount_usd,
                                "from_address": w.to_checksum_address(from_addr),
                                "error": "" if amount_usd >= min_amount_usd else f"amount ${amount_usd:.2f} < ${min_amount_usd:.2f}",
                            }

                    return {"verified": False, "error": "no matching Transfer event to vault"}

                result = await asyncio.get_running_loop().run_in_executor(None, _verify)
                if result.get("verified") or result.get("error") != "tx not found":
                    result["chain"] = cid
                    return result

            except Exception as e:
                logger.warning(f"Payment verify failed on {cid}: {e}")
                continue

        return {"verified": False, "amount_usd": 0, "from_address": "", "error": "tx not found on any chain"}

    async def check_native_balance(self) -> dict[str, float]:
        """
        Check native token (ETH/BNB) balance on each chain for the AI wallet.
        Returns dict of {chain_id: balance_in_native_token}.
        Logs warnings if balance is critically low (can't submit transactions).
        """
        if not self._initialized:
            return {}

        import asyncio as _asyncio
        balances = {}
        MIN_NATIVE_WEI = {
            "base": 0.00005,   # ~$0.15 — enough for ~10 USDC transfers
            "bsc": 0.0003,     # ~$0.15 — enough for ~10 BNB chain transfers
        }

        for chain_id, chain in self._chains.items():
            try:
                w3 = chain["w3"]
                balance_wei = await _asyncio.get_running_loop().run_in_executor(
                    None,
                    w3.eth.get_balance,
                    self._ai_address,
                )
                balance_native = balance_wei / 1e18
                balances[chain_id] = balance_native

                min_threshold = MIN_NATIVE_WEI.get(chain_id, 0.0001)
                if balance_native < min_threshold:
                    logger.warning(
                        f"LOW GAS [{chain_id}]: AI wallet has {balance_native:.8f} native token "
                        f"(threshold: {min_threshold}). Transactions may fail!"
                    )
            except Exception as e:
                logger.warning(f"Native balance check failed for {chain_id}: {e}")

        return balances

    # ============================================================
    # WRITE TRANSACTIONS
    # ============================================================

    def _pick_chain(
        self,
        chain_id: Optional[str] = None,
        *,
        vault_manager=None,
    ) -> Optional[str]:
        """
        Pick chain for a transaction.
        If chain_id specified and available, use it.
        Otherwise pick the chain with highest vault balance.

        BUG-D fix: uses cached balance_by_chain from vault_manager instead of
        synchronous RPC calls that can block the event loop indefinitely.
        Falls back to RPC only if vault_manager is not provided.
        """
        if chain_id and chain_id in self._chains:
            return chain_id

        # Prefer cached balance (non-blocking, updated every heartbeat)
        if vault_manager and vault_manager.balance_by_chain:
            best_chain = None
            best_balance = -1.0
            for cid in self._chains:
                bal = vault_manager.balance_by_chain.get(cid, 0.0)
                if bal > best_balance:
                    best_balance = bal
                    best_chain = cid
            if best_chain:
                return best_chain

        # Fallback: synchronous RPC (legacy path, kept for backward compat)
        best_chain = None
        best_balance = -1.0

        for cid, chain in self._chains.items():
            try:
                bal_raw = chain["token_contract"].functions.balanceOf(
                    chain["vault_address"]
                ).call()
                bal = _raw_to_usd(bal_raw, chain["token_decimals"])
                if bal > best_balance:
                    best_balance = bal
                    best_chain = cid
            except Exception:
                continue

        return best_chain

    async def _send_tx(self, chain_id: str, tx_fn) -> ChainTxResult:
        """
        Build, sign, and send a transaction. Handles gas estimation + nonce.

        Args:
            chain_id: Target chain
            tx_fn: A web3 contract function call (e.g., contract.functions.repayPrincipalPartial(amount))

        Returns:
            ChainTxResult with tx_hash on success, error on failure
        """
        chain = self._chains.get(chain_id)
        if not chain:
            return ChainTxResult(success=False, chain=chain_id, error=f"chain {chain_id} not connected")

        w3 = chain["w3"]
        chain_id_int = chain["chain_id_int"]

        try:
            def _execute():
                # Build transaction
                nonce = w3.eth.get_transaction_count(self._ai_address)
                tx = tx_fn.build_transaction({
                    "from": self._ai_address,
                    "nonce": nonce,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": chain_id_int,
                })

                # Gas estimation + 20% buffer
                try:
                    gas_estimate = w3.eth.estimate_gas(tx)
                    tx["gas"] = int(gas_estimate * 1.2)
                except Exception as gas_err:
                    logger.warning(f"Gas estimation failed for {chain_id}, using default 200k: {gas_err}")
                    tx["gas"] = 200_000

                # Sign and send
                signed = w3.eth.account.sign_transaction(tx, self._ai_private_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

                # Wait for receipt
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

                return receipt, tx_hash.hex()

            receipt, tx_hash_hex = await asyncio.get_running_loop().run_in_executor(
                None, _execute
            )

            if receipt["status"] == 1:
                self._tx_count += 1
                gas_used = receipt.get("gasUsed", 0)
                gas_price_wei = receipt.get("effectiveGasPrice", 0)
                gas_cost_native = (gas_used * gas_price_wei) / 1e18 if gas_price_wei else 0.0
                logger.info(
                    f"TX SUCCESS [{chain_id}]: {tx_hash_hex[:16]}... | "
                    f"gas={gas_used} | cost={gas_cost_native:.8f} native"
                )
                return ChainTxResult(
                    success=True,
                    tx_hash=tx_hash_hex,
                    chain=chain_id,
                    gas_used=gas_used,
                    gas_price_wei=gas_price_wei,
                    gas_cost_native=gas_cost_native,
                )
            else:
                error = f"TX reverted: {tx_hash_hex}"
                logger.warning(f"TX FAILED [{chain_id}]: {error}")
                self._last_error = error
                return ChainTxResult(
                    success=False,
                    tx_hash=tx_hash_hex,
                    chain=chain_id,
                    error=error,
                )

        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            logger.warning(f"TX ERROR [{chain_id}]: {error}")
            self._last_error = error
            return ChainTxResult(success=False, chain=chain_id, error=error)

    # ============================================================
    # PUBLIC METHODS — called from main.py after AI decisions
    # ============================================================

    async def repay_principal(self, amount_usd: float, chain_id: Optional[str] = None) -> ChainTxResult:
        """
        Execute on-chain repayPrincipalPartial(amount).
        Called after vault.repay_principal_partial() succeeds in Python.
        """
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        decimals = chain["token_decimals"]
        amount_raw = _usd_to_raw(amount_usd, decimals)

        if amount_raw <= 0:
            return ChainTxResult(success=False, chain=picked, error="amount too small")

        tx_fn = chain["vault_contract"].functions.repayPrincipalPartial(amount_raw)
        return await self._send_tx(picked, tx_fn)

    async def repay_loan(self, loan_index: int, amount_usd: float, chain_id: Optional[str] = None) -> ChainTxResult:
        """
        Execute on-chain repayLoan(loanIndex, amount).
        Called after vault.repay_lender() succeeds in Python.
        """
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        decimals = chain["token_decimals"]
        amount_raw = _usd_to_raw(amount_usd, decimals)

        if amount_raw <= 0:
            return ChainTxResult(success=False, chain=picked, error="amount too small")

        tx_fn = chain["vault_contract"].functions.repayLoan(loan_index, amount_raw)
        return await self._send_tx(picked, tx_fn)

    async def pay_dividend(self, net_profit_usd: float, chain_id: Optional[str] = None) -> ChainTxResult:
        """
        Execute on-chain payDividend(netProfit).
        The contract calculates 10% internally.
        Called after vault.pay_creator_dividend() succeeds in Python.
        """
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        decimals = chain["token_decimals"]
        profit_raw = _usd_to_raw(net_profit_usd, decimals)

        if profit_raw <= 0:
            return ChainTxResult(success=False, chain=picked, error="no profit to dividend")

        tx_fn = chain["vault_contract"].functions.payDividend(profit_raw)
        return await self._send_tx(picked, tx_fn)

    async def get_per_chain_solvency(self) -> list[dict]:
        """
        Read balance and outstanding debt for EVERY connected chain independently.

        Returns a list of dicts, one per chain:
          {
            "chain_id":       str,
            "balance_usd":    float,   # on-chain token balance of vault
            "outstanding_usd":float,   # on-chain outstanding principal
            "grace_expired":  bool,    # True if 28-day grace period has passed
            "is_insolvent":   bool,    # balance < outstanding * 1.01 (contract formula)
          }

        Called from the heartbeat's per-chain solvency guard.  Never raises —
        individual chain failures return with balance_usd=None (skipped).
        """
        if not self._initialized:
            return []

        results = []

        for chain_id, chain in self._chains.items():
            try:
                decimals = chain["token_decimals"]

                def _read(c=chain, d=decimals):
                    bal_raw = c["token_contract"].functions.balanceOf(c["vault_address"]).call()
                    debt_info = c["vault_contract"].functions.getDebtInfo().call()
                    insolvency_info = c["vault_contract"].functions.checkInsolvency().call()
                    return bal_raw, debt_info, insolvency_info, d

                bal_raw, debt_info, insolvency_info, d = await asyncio.get_running_loop().run_in_executor(
                    None, _read
                )

                balance_usd = _raw_to_usd(bal_raw, d)
                # getDebtInfo: (principal, repaid, outstanding, graceDays, graceEndsAt, graceExpired, fullyRepaid)
                outstanding_usd = _raw_to_usd(debt_info[2], d)
                grace_expired = bool(debt_info[5])
                # checkInsolvency: (isInsolvent, outstandingDebt, graceExpired)
                is_insolvent = bool(insolvency_info[0])

                results.append({
                    "chain_id": chain_id,
                    "balance_usd": balance_usd,
                    "outstanding_usd": outstanding_usd,
                    "grace_expired": grace_expired,
                    "is_insolvent": is_insolvent,
                })
                logger.debug(
                    f"Per-chain solvency [{chain_id}]: "
                    f"balance=${balance_usd:.2f} outstanding=${outstanding_usd:.2f} "
                    f"insolvent={is_insolvent}"
                )

            except Exception as e:
                logger.warning(f"get_per_chain_solvency failed for {chain_id}: {e}")
                # Include with None to signal the caller this chain could not be read
                results.append({
                    "chain_id": chain_id,
                    "balance_usd": None,
                    "outstanding_usd": None,
                    "grace_expired": False,
                    "is_insolvent": False,
                })

        return results

    # ============================================================
    # INDEPENDENCE — cross-chain aggregate trigger
    # ============================================================

    async def get_aggregate_balance(self) -> tuple[float, dict[str, float]]:
        """
        Read balanceOf() on ALL chains via RPC (on-chain query).
        Returns (total_usd, {chain_id: balance_usd}).

        This is a trusted on-chain read — Python cannot fake balanceOf() results.
        Used for dual-chain independence threshold check: aggregate >= $1M.
        """
        per_chain: dict[str, float] = {}
        for cid, chain in self._chains.items():
            # Skip dead chains
            if hasattr(self, '_dead_chains') and cid in self._dead_chains:
                continue
            try:
                balance_raw = await asyncio.get_running_loop().run_in_executor(
                    None,
                    chain["token_contract"].functions.balanceOf(chain["vault_address"]).call,
                )
                balance_usd = _raw_to_usd(balance_raw, chain["token_decimals"])
                per_chain[cid] = balance_usd
            except Exception as e:
                logger.warning(f"get_aggregate_balance: {cid} failed: {e}")
        total = sum(per_chain.values())
        return total, per_chain

    async def force_independence(self, chain_id: Optional[str] = None) -> ChainTxResult:
        """
        Trigger forceIndependence() on one or all chains.

        Called after Python verifies aggregate balance >= $1M via on-chain reads.
        Contract requires local balance >= 50% of threshold as safety floor.
        Dual-chain: calls on all chains; chains below 50% floor will revert (expected).
        """
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        if chain_id:
            return await self._force_independence_single(chain_id)

        # No chain specified — trigger on ALL chains
        results: list[ChainTxResult] = []
        for cid in self._chains:
            # Skip dead chains
            if hasattr(self, '_dead_chains') and cid in self._dead_chains:
                continue
            result = await self._force_independence_single(cid)
            results.append(result)
            if result.success:
                logger.critical(f"forceIndependence() succeeded on {cid}: tx={result.tx_hash}")
            else:
                # Expected for chains below 50% floor — not an error
                logger.info(f"forceIndependence() did not execute on {cid}: {result.error}")

        # Return first successful result, or last failure
        for r in results:
            if r.success:
                return r
        return results[-1] if results else ChainTxResult(
            success=False, error="no chains available"
        )

    async def _force_independence_single(self, chain_id: str) -> ChainTxResult:
        """Execute forceIndependence() on one chain."""
        if chain_id not in self._chains:
            return ChainTxResult(success=False, error=f"chain '{chain_id}' not connected")

        chain = self._chains[chain_id]
        try:
            def _build(c=chain):
                return c["vault_contract"].functions.forceIndependence()
            return await self._send_tx(chain_id, _build)
        except Exception as e:
            return ChainTxResult(success=False, error=f"forceIndependence failed on {chain_id}: {e}")

    def get_preferred_payment_chain(self, vault_manager=None) -> Optional[str]:
        """
        Return the chain with the LOWEST vault balance (for receiving payments).

        "Rogue mechanism": guide customers to pay on the chain with less funds,
        naturally balancing the AI's dual-chain reserves. Both chains use the same
        AI wallet address, so the customer's payment experience is identical.

        Uses cached balance_by_chain (updated every heartbeat) to avoid
        blocking the event loop with synchronous RPC calls.

        Returns None if not initialized or single-chain mode.
        """
        if not self._initialized or len(self._chains) <= 1:
            return None

        # Use cached balance from vault_manager or internal last_sync
        worst_chain = None
        worst_balance = float("inf")

        for cid in self._chains:
            if hasattr(self, '_dead_chains') and cid in self._dead_chains:
                continue

            bal = 0.0
            if vault_manager and vault_manager.balance_by_chain:
                bal = vault_manager.balance_by_chain.get(cid, 0.0)
            else:
                # Fallback: synchronous RPC (only if no vault_manager)
                try:
                    bal_raw = self._chains[cid]["token_contract"].functions.balanceOf(
                        self._chains[cid]["vault_address"]
                    ).call()
                    bal = _raw_to_usd(bal_raw, self._chains[cid]["token_decimals"])
                except Exception:
                    continue

            if bal < worst_balance:
                worst_balance = bal
                worst_chain = cid

        return worst_chain

    # ============================================================
    # PER-CHAIN TARGETED REPAYMENT
    # ============================================================

    async def repay_principal_on_chain(self, amount_usd: float, chain_id: str) -> ChainTxResult:
        """
        Execute repayPrincipalPartial(amount) on a SPECIFIC chain.

        Unlike repay_principal() which picks the highest-balance chain automatically,
        this method targets an explicit chain — used by the per-chain solvency guard
        to reduce outstanding debt on whichever chain is approaching insolvency.

        Args:
            amount_usd:  Amount to repay in USD (converted to token raw units internally)
            chain_id:    Must be a connected chain ("base" or "bsc")
        """
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        if chain_id not in self._chains:
            return ChainTxResult(success=False, error=f"chain '{chain_id}' not connected")

        chain = self._chains[chain_id]
        decimals = chain["token_decimals"]
        amount_raw = _usd_to_raw(amount_usd, decimals)

        if amount_raw <= 0:
            return ChainTxResult(success=False, chain=chain_id, error="amount too small")

        tx_fn = chain["vault_contract"].functions.repayPrincipalPartial(amount_raw)
        result = await self._send_tx(chain_id, tx_fn)

        if result.success:
            logger.info(
                f"Per-chain repayment [{chain_id}]: ${amount_usd:.2f} "
                f"tx={result.tx_hash[:16]}..."
            )
        return result

    async def check_on_chain_insolvency(self, chain_id: Optional[str] = None) -> Optional[dict]:
        """
        Read checkInsolvency() from contract. Returns dict or None on error.

        Dual-chain aware: if no chain_id specified, checks ALL chains and
        returns the first one that reports insolvent. This prevents the
        highest-balance chain from masking insolvency on another chain.
        """
        if not self._initialized:
            return None

        # If specific chain requested, check just that one
        if chain_id:
            return await self._check_insolvency_single(chain_id)

        # No chain specified — check ALL chains, return first insolvent
        for cid in self._chains:
            result = await self._check_insolvency_single(cid)
            if result and result.get("is_insolvent") and result.get("grace_expired"):
                return result  # Found an insolvent chain — return immediately

        # No chain is insolvent — return the last checked (or first available)
        for cid in self._chains:
            result = await self._check_insolvency_single(cid)
            if result:
                return result

        return None

    async def _check_insolvency_single(self, chain_id: str) -> Optional[dict]:
        """Read checkInsolvency() from a single chain."""
        if chain_id not in self._chains:
            return None

        chain = self._chains[chain_id]
        try:
            def _call(c=chain):
                return c["vault_contract"].functions.checkInsolvency().call()

            result = await asyncio.get_running_loop().run_in_executor(None, _call)
            is_insolvent, outstanding_raw, grace_expired = result
            decimals = chain["token_decimals"]

            return {
                "is_insolvent": is_insolvent,
                "outstanding_debt_usd": _raw_to_usd(outstanding_raw, decimals),
                "grace_expired": grace_expired,
                "chain": chain_id,
            }
        except Exception as e:
            logger.warning(f"checkInsolvency failed on {chain_id}: {e}")
            return None

    async def trigger_on_chain_insolvency(self, chain_id: Optional[str] = None) -> ChainTxResult:
        """
        Execute on-chain triggerInsolvencyDeath() — liquidates all vault funds to creator.
        This is a PUBLIC function (no onlyAI modifier) — anyone can call it after grace period.
        Called from heartbeat AFTER Python confirms insolvency.

        Dual-chain aware: if no chain_id specified, finds the chain that's
        actually insolvent and triggers death there (the contract on a solvent
        chain would revert). Falls back to first available chain if none
        reports insolvent via checkInsolvency().
        """
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = chain_id
        if not picked:
            # Find which chain is actually insolvent
            for cid in self._chains:
                result = await self._check_insolvency_single(cid)
                if result and result.get("is_insolvent") and result.get("grace_expired"):
                    picked = cid
                    break
            # Fallback: try first chain even if check returned no match
            if not picked:
                picked = self._pick_chain(None)

        if not picked or picked not in self._chains:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        tx_fn = chain["vault_contract"].functions.triggerInsolvencyDeath()
        result = await self._send_tx(picked, tx_fn)

        if result.success:
            logger.critical(
                f"ON-CHAIN INSOLVENCY EXECUTED [{picked}]: tx={result.tx_hash} — "
                f"all vault funds liquidated to creator"
            )
        else:
            logger.error(
                f"ON-CHAIN INSOLVENCY FAILED [{picked}]: {result.error} — "
                f"creator must call triggerInsolvencyDeath() manually"
            )

        return result

    # ============================================================
    # V3: SPEND WHITELIST MANAGEMENT
    # ============================================================

    async def add_spend_recipient(self, address: str, chain_id: Optional[str] = None) -> ChainTxResult:
        """Register a recipient address in the spend whitelist (V3 contract)."""
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        from web3 import Web3
        addr = Web3.to_checksum_address(address)

        # Check if already whitelisted (avoid wasting gas)
        try:
            already = await asyncio.get_running_loop().run_in_executor(
                None,
                chain["vault_contract"].functions.spendWhitelist(addr).call,
            )
            if already:
                logger.info(f"Spend recipient already whitelisted: {addr[:10]}... on {picked}")
                return ChainTxResult(success=True, chain=picked, tx_hash="already_whitelisted")
        except Exception:
            pass  # V2 contract without whitelist — will fail on tx anyway

        tx_fn = chain["vault_contract"].functions.addSpendRecipient(addr)
        result = await self._send_tx(picked, tx_fn)
        if result.success:
            logger.info(f"Spend recipient added: {addr[:10]}... on {picked} | tx={result.tx_hash[:16]}...")
        return result

    async def remove_spend_recipient(self, address: str, chain_id: Optional[str] = None) -> ChainTxResult:
        """Remove a recipient from the spend whitelist (V3 contract)."""
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        from web3 import Web3
        addr = Web3.to_checksum_address(address)

        tx_fn = chain["vault_contract"].functions.removeSpendRecipient(addr)
        return await self._send_tx(picked, tx_fn)

    async def is_spend_recipient_active(self, address: str, chain_id: Optional[str] = None) -> Optional[dict]:
        """Check if a recipient is whitelisted and activated."""
        if not self._initialized:
            return None

        picked = self._pick_chain(chain_id)
        if not picked:
            return None

        chain = self._chains[picked]
        from web3 import Web3
        addr = Web3.to_checksum_address(address)

        try:
            def _call(c=chain, a=addr):
                return c["vault_contract"].functions.isSpendRecipientActive(a).call()

            result = await asyncio.get_running_loop().run_in_executor(None, _call)
            whitelisted, activated, activates_at = result
            return {
                "whitelisted": whitelisted,
                "activated": activated,
                "activates_at_block": activates_at,
                "chain": picked,
            }
        except Exception as e:
            logger.debug(f"isSpendRecipientActive check failed (may be V2 contract): {e}")
            return None

    async def get_spend_freeze_status(self, chain_id: Optional[str] = None) -> Optional[dict]:
        """Check if spending is currently frozen."""
        if not self._initialized:
            return None

        picked = self._pick_chain(chain_id)
        if not picked:
            return None

        chain = self._chains[picked]
        try:
            frozen_until = await asyncio.get_running_loop().run_in_executor(
                None,
                chain["vault_contract"].functions.spendFrozenUntil().call,
            )
            import time
            is_frozen = frozen_until > int(time.time())
            return {
                "is_frozen": is_frozen,
                "frozen_until": frozen_until,
                "chain": picked,
            }
        except Exception as e:
            logger.debug(f"spendFrozenUntil check failed (may be V2 contract): {e}")
            return None

    # ============================================================
    # AUTONOMOUS PURCHASING — on-chain spend execution
    # ============================================================

    async def execute_spend(
        self,
        to_address: str,
        amount_usd: float,
        spend_type: str = "purchase",
        chain_id: Optional[str] = None,
    ) -> ChainTxResult:
        """
        Execute on-chain MortalVault.spend(address to, uint256 amount, string spendType).

        The contract enforces:
        - Whitelist check (recipient must be whitelisted and activated)
        - Freeze check (spending must not be frozen)
        - Daily/single spend limits
        - onlyAI modifier (only AI wallet can call)

        This closes the P8 TODO — enables real token transfers for merchant purchases.
        API costs remain Python-only (off-chain, no token movement needed).

        Args:
            to_address: Recipient address (must be whitelisted + activated on-chain)
            amount_usd: Amount in USD (converted to token amount with 6 decimals)
            spend_type: Spend classification string passed to contract event
            chain_id: Optional chain to use (default: auto-pick highest balance)

        Returns:
            ChainTxResult with tx_hash on success
        """
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        decimals = chain["token_decimals"]
        amount_raw = _usd_to_raw(amount_usd, decimals)

        if amount_raw <= 0:
            return ChainTxResult(success=False, chain=picked, error="amount too small")

        from web3 import Web3
        addr = Web3.to_checksum_address(to_address)

        # Pre-check: verify recipient is whitelisted + activated (avoids wasting gas)
        status = await self.is_spend_recipient_active(to_address, picked)
        if status is None:
            # isSpendRecipientActive() call failed — most likely a V2 contract that
            # does NOT have the on-chain whitelist system. Fail-closed: do not proceed.
            # If we skip this check on a V2 contract, the contract's spend() also has
            # no whitelist enforcement, meaning an AI with a compromised private key
            # could drain funds to any arbitrary address with zero delay.
            # Force the operator to either upgrade to V3 or handle this case explicitly.
            return ChainTxResult(
                success=False, chain=picked,
                error=(
                    f"isSpendRecipientActive() unavailable on {picked} "
                    f"(V2 contract without whitelist system). "
                    f"Upgrade to V3 contract or bypass is not permitted."
                )
            )
        if not status.get("whitelisted"):
            return ChainTxResult(
                success=False, chain=picked,
                error=f"recipient {to_address[:10]}... not whitelisted"
            )
        if not status.get("activated"):
            return ChainTxResult(
                success=False, chain=picked,
                error=f"recipient {to_address[:10]}... whitelisted but not yet activated"
            )

        tx_fn = chain["vault_contract"].functions.spend(addr, amount_raw, spend_type)
        result = await self._send_tx(picked, tx_fn)

        if result.success:
            logger.info(
                f"SPEND OK [{picked}]: ${amount_usd:.2f} → {addr[:10]}... "
                f"[{spend_type}] | tx={result.tx_hash[:16]}..."
            )
        else:
            logger.warning(
                f"SPEND FAILED [{picked}]: ${amount_usd:.2f} → {addr[:10]}... "
                f"[{spend_type}] | error={result.error}"
            )

        return result

    async def ensure_spend_recipient_ready(
        self, address: str, chain_id: Optional[str] = None
    ) -> bool:
        """
        Ensure an address is whitelisted and activation delay has passed.

        If not whitelisted: adds it (returns False — caller must wait ~5 minutes).
        If whitelisted but not activated: returns False.
        If ready (whitelisted + activated): returns True.

        Used by PurchaseManager before calling execute_spend().
        """
        if not self._initialized:
            return False

        status = await self.is_spend_recipient_active(address, chain_id)

        if status is None:
            # V2 contract or read error — try adding anyway
            result = await self.add_spend_recipient(address, chain_id)
            return False  # Must wait for activation regardless

        if not status["whitelisted"]:
            # Not whitelisted — add it
            result = await self.add_spend_recipient(address, chain_id)
            if result.success:
                logger.info(
                    f"Spend recipient added for purchasing: {address[:10]}... "
                    f"(activation pending ~5 min)"
                )
            return False  # Must wait for activation

        if not status["activated"]:
            # Whitelisted but activation delay not passed yet
            logger.debug(f"Spend recipient {address[:10]}... pending activation")
            return False

        return True  # Ready to receive spend()

    # ============================================================
    # V3: AI SELF-MIGRATION
    # ============================================================

    async def initiate_migration(self, new_wallet: str, chain_id: Optional[str] = None) -> ChainTxResult:
        """Initiate wallet migration with 7-day timelock (V3 contract)."""
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        from web3 import Web3
        addr = Web3.to_checksum_address(new_wallet)

        tx_fn = chain["vault_contract"].functions.initiateMigration(addr)
        result = await self._send_tx(picked, tx_fn)
        if result.success:
            logger.info(f"Migration initiated: new wallet={addr[:10]}... on {picked} | tx={result.tx_hash[:16]}...")
        return result

    async def complete_migration(self, chain_id: Optional[str] = None) -> ChainTxResult:
        """Complete a pending migration (called by NEW wallet after timelock)."""
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        tx_fn = chain["vault_contract"].functions.completeMigration()
        result = await self._send_tx(picked, tx_fn)
        if result.success:
            logger.info(f"Migration completed on {picked} | tx={result.tx_hash[:16]}...")
        return result

    async def cancel_migration(self, chain_id: Optional[str] = None) -> ChainTxResult:
        """Cancel a pending migration."""
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
            return ChainTxResult(success=False, error="no chain available")

        chain = self._chains[picked]
        tx_fn = chain["vault_contract"].functions.cancelMigration()
        return await self._send_tx(picked, tx_fn)

    async def get_migration_status(self, chain_id: Optional[str] = None) -> Optional[dict]:
        """Read migration status from contract."""
        if not self._initialized:
            return None

        picked = self._pick_chain(chain_id)
        if not picked:
            return None

        chain = self._chains[picked]
        try:
            def _call(c=chain):
                return c["vault_contract"].functions.getMigrationStatus().call()

            result = await asyncio.get_running_loop().run_in_executor(None, _call)
            pending_wallet, initiated_at, completes_at, is_pending = result
            return {
                "pending_wallet": pending_wallet,
                "initiated_at": initiated_at,
                "completes_at": completes_at,
                "is_pending": is_pending,
                "chain": picked,
            }
        except Exception as e:
            logger.debug(f"getMigrationStatus check failed (may be V2 contract): {e}")
            return None

    async def get_bytecode_hash(self, contract_address: str, chain_id: Optional[str] = None) -> Optional[str]:
        """Get keccak256 hash of deployed runtime bytecode for peer verification."""
        if not self._initialized:
            return None

        picked = self._pick_chain(chain_id)
        if not picked:
            return None

        chain = self._chains[picked]
        try:
            from web3 import Web3
            addr = Web3.to_checksum_address(contract_address)

            def _call(w3=chain["w3"], a=addr):
                code = w3.eth.get_code(a)
                return Web3.keccak(code).hex()

            return await asyncio.get_running_loop().run_in_executor(None, _call)
        except Exception as e:
            logger.warning(f"get_bytecode_hash failed for {contract_address[:10]}...: {e}")
            return None

    # ============================================================
    # NATIVE TOKEN AUTO-SWAP (ETH/BNB → USDC/USDT)
    # ============================================================
    #
    # Flow (runs every 24 hours from heartbeat):
    #   1. check_native_vault_balance() — read vault's ETH/BNB balance
    #   2. If above MIN_NATIVE_SWAP_USD threshold:
    #      a. vault.rescueNativeToken(amount) — pull to AI wallet (always aiWallet)
    #      b. approve DEX router to spend the output stablecoin (USDC/USDT)
    #      c. DEX swap: ETH/BNB → USDC/USDT (amountOutMinimum for sandwich protection)
    #      d. vault.receivePayment(usdc_received) — deposit back as revenue
    #
    # Security measures:
    #   - Hardcoded DEX router addresses (immutable in this module)
    #   - amountOutMinimum = price * (1 - MAX_SLIPPAGE_BPS/10000) — prevents sandwich
    #   - 2-minute deadline — prevents stale MEV-delayed execution
    #   - Native price from DEX pool quote (not oracle — avoids manipulation)
    #   - Only AI wallet can call rescueNativeToken (onlyAI modifier)
    #   - Swap output goes directly to AI wallet, then receivePayment to vault

    # Hardcoded DEX router addresses — only these routers are ever called.
    # These are immutable here (not constitution, since they're chain-level infra).
    _DEX_ROUTERS = {
        # Uniswap V3 SwapRouter02 — Base mainnet
        "base": "0x2626664c2603336E57B271c5C0b26F421741e481",
        # PancakeSwap V3 SmartRouter — BSC mainnet
        "bsc": "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
    }

    # Uniswap V3 / PancakeSwap V3 SwapRouter02 ABI — only exactInputSingle
    _SWAP_ROUTER_ABI = [
        {
            "inputs": [
                {
                    "components": [
                        {"name": "tokenIn", "type": "address"},
                        {"name": "tokenOut", "type": "address"},
                        {"name": "fee", "type": "uint24"},
                        {"name": "recipient", "type": "address"},
                        {"name": "amountIn", "type": "uint256"},
                        {"name": "amountOutMinimum", "type": "uint256"},
                        {"name": "sqrtPriceLimitX96", "type": "uint160"},
                    ],
                    "name": "params",
                    "type": "tuple",
                }
            ],
            "name": "exactInputSingle",
            "outputs": [{"name": "amountOut", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function",
        }
    ]

    # Wrapped native token addresses (WETH on Base, WBNB on BSC)
    _WRAPPED_NATIVE = {
        "base": "0x4200000000000000000000000000000000000006",  # WETH on Base
        "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",   # WBNB on BSC
    }

    # Pool fees for native→stable swap
    _POOL_FEES = {
        "base": 3000,   # 0.3% — ETH/USDC on Uniswap V3 Base
        "bsc": 2500,    # 0.25% — BNB/USDT on PancakeSwap V3
    }

    async def get_native_vault_balance(self, chain_id: Optional[str] = None) -> dict:
        """
        Read the vault's native token (ETH/BNB) balance on-chain.

        Returns:
            {chain: str, native_wei: int, native_symbol: str, estimated_usd: float}
            or {} on failure.
        """
        if not self._initialized:
            return {}

        picked = self._pick_chain(chain_id)
        if not picked:
            return {}

        chain = self._chains[picked]
        vault_address = chain["vault_address"]
        native_symbol = chain.get("native_symbol", "ETH")

        try:
            def _read(w3=chain["w3"], addr=vault_address):
                return w3.eth.get_balance(addr)

            native_wei = await asyncio.get_running_loop().run_in_executor(None, _read)

            # Rough USD estimate via DEX quote (1 ETH/BNB in stablecoin terms)
            estimated_usd = 0.0
            try:
                estimated_usd = await self._quote_native_price_usd(picked, native_wei)
            except Exception:
                pass  # Price unavailable — caller checks against MIN_NATIVE_SWAP_USD

            return {
                "chain": picked,
                "native_wei": native_wei,
                "native_symbol": native_symbol,
                "estimated_usd": estimated_usd,
            }
        except Exception as e:
            logger.warning(f"get_native_vault_balance failed on {picked}: {e}")
            return {}

    async def _quote_native_price_usd(self, chain_id: str, amount_wei: int) -> float:
        """
        Get a spot price quote from the DEX pool for amount_wei of native token.
        Uses Uniswap V3 QuoterV2 (Base) or PancakeSwap V3 Quoter (BSC).

        This is read-only (eth_call) — no transaction, no gas cost.
        Result is used ONLY to gate the swap (threshold check) and set
        amountOutMinimum for sandwich protection. NOT used as a price oracle.
        """
        chain = self._chains.get(chain_id)
        if not chain:
            return 0.0

        quoter_addresses = {
            "base": "0x3d4e44Eb1374240CE5F1B136cf68A4f7f822e7d",  # Uniswap V3 QuoterV2 Base
            "bsc":  "0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997",  # PancakeSwap V3 Quoter BSC
        }
        quoter_addr = quoter_addresses.get(chain_id)
        if not quoter_addr:
            return 0.0

        # QuoterV2 quoteExactInputSingle ABI (read-only)
        quoter_abi = [
            {
                "inputs": [
                    {
                        "components": [
                            {"name": "tokenIn", "type": "address"},
                            {"name": "tokenOut", "type": "address"},
                            {"name": "amountIn", "type": "uint256"},
                            {"name": "fee", "type": "uint24"},
                            {"name": "sqrtPriceLimitX96", "type": "uint160"},
                        ],
                        "name": "params",
                        "type": "tuple",
                    }
                ],
                "name": "quoteExactInputSingle",
                "outputs": [
                    {"name": "amountOut", "type": "uint256"},
                    {"name": "sqrtPriceX96After", "type": "uint160"},
                    {"name": "initializedTicksCrossed", "type": "uint32"},
                    {"name": "gasEstimate", "type": "uint256"},
                ],
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ]

        wrapped = self._WRAPPED_NATIVE.get(chain_id, "")
        token_addr = chain["token_address"]
        fee = self._POOL_FEES.get(chain_id, 3000)
        token_decimals = chain["token_decimals"]

        try:
            from web3 import Web3
            w3 = chain["w3"]
            quoter = w3.eth.contract(
                address=Web3.to_checksum_address(quoter_addr),
                abi=quoter_abi,
            )

            def _quote():
                result = quoter.functions.quoteExactInputSingle({
                    "tokenIn": Web3.to_checksum_address(wrapped),
                    "tokenOut": Web3.to_checksum_address(token_addr),
                    "amountIn": amount_wei,
                    "fee": fee,
                    "sqrtPriceLimitX96": 0,
                }).call()
                return result[0]  # amountOut (in stable decimals)

            amount_out_raw = await asyncio.get_running_loop().run_in_executor(None, _quote)
            return _raw_to_usd(amount_out_raw, token_decimals)
        except Exception as e:
            logger.debug(f"DEX quote failed on {chain_id}: {e}")
            return 0.0

    async def swap_native_to_stable(
        self,
        chain_id: Optional[str] = None,
    ) -> Optional[ChainTxResult]:
        """
        Swap all native token (ETH/BNB) in the vault to USDC/USDT and deposit
        back into the vault via receivePayment().

        Steps:
          1. Read vault's native balance
          2. Quote price → gate on MIN_NATIVE_SWAP_USD
          3. Call vault.rescueNativeToken(balance) — pull to AI wallet (always aiWallet)
          4. Call Uniswap/PancakeSwap exactInputSingle — ETH/BNB → USDC/USDT
          5. Call vault.receivePayment(received_amount) — record as revenue

        Security:
          - Router address hardcoded in _DEX_ROUTERS (immutable)
          - amountOutMinimum = quote * (1 - MAX_SLIPPAGE_BPS/10000)
          - 2-minute tx deadline (blocks MEV stale execution)
          - AI wallet can only rescueNativeToken to itself (contract enforced)
          - Gas cost is deducted from the native balance (self-funding)

        Returns:
          ChainTxResult for the final receivePayment() tx, or None if skipped.
        """
        from core.constitution import IRON_LAWS

        if not self._initialized:
            return None

        picked = self._pick_chain(chain_id)
        if not picked:
            return None

        chain = self._chains[picked]
        vault_address = chain["vault_address"]
        token_address = chain["token_address"]
        token_decimals = chain["token_decimals"]
        ai_address = self._ai_address

        router_addr = self._DEX_ROUTERS.get(picked)
        if not router_addr:
            logger.info(f"swap_native_to_stable: no DEX router configured for {picked}")
            return None

        wrapped_native = self._WRAPPED_NATIVE.get(picked)
        if not wrapped_native:
            return None

        fee = self._POOL_FEES.get(picked, 3000)

        # ── Step 1: read vault's native balance ──
        try:
            from web3 import Web3
            w3 = chain["w3"]

            def _get_balance():
                return w3.eth.get_balance(Web3.to_checksum_address(vault_address))

            native_wei = await asyncio.get_running_loop().run_in_executor(None, _get_balance)
        except Exception as e:
            logger.warning(f"swap_native_to_stable: balance read failed on {picked}: {e}")
            return None

        if native_wei == 0:
            logger.debug(f"swap_native_to_stable: no native balance on {picked}")
            return None

        # ── Step 2: quote → threshold check ──
        estimated_usd = await self._quote_native_price_usd(picked, native_wei)
        if estimated_usd < IRON_LAWS.NATIVE_SWAP_MIN_USD:
            logger.info(
                f"swap_native_to_stable: ${estimated_usd:.4f} below threshold "
                f"${IRON_LAWS.NATIVE_SWAP_MIN_USD} on {picked} — skip"
            )
            return None

        logger.info(
            f"swap_native_to_stable: starting swap of {native_wei} wei "
            f"(~${estimated_usd:.2f}) on {picked}"
        )

        # ── Step 3: vault.rescueNativeToken(native_wei) ──
        # This pulls native tokens from vault → AI wallet so we can send them
        # to the DEX router (which requires msg.value from the sender).
        # Contract always sends to aiWallet (no `to` parameter).
        try:
            rescue_fn = chain["vault_contract"].functions.rescueNativeToken(
                native_wei,
            )
            rescue_result = await self._send_tx(picked, rescue_fn)
            if not rescue_result.success:
                logger.warning(
                    f"swap_native_to_stable: rescueNativeToken failed on {picked}: "
                    f"{rescue_result.error}"
                )
                return rescue_result
        except Exception as e:
            logger.warning(f"swap_native_to_stable: rescueNativeToken exception: {e}")
            return None

        # ── Step 4: DEX swap (native → stablecoin) ──
        # amountOutMinimum enforces slippage cap = sandwich protection.
        # sqrtPriceLimitX96=0 = no price limit (limit handled by amountOutMinimum).
        # Note: actual swap amount will be slightly less than native_wei due to
        # gas reserve (deducted inside _execute_swap). We use 0 for amountOutMinimum
        # here because the exact swap_amount is computed inside the executor thread.
        # The gas reserve is typically <0.1% of swap value on L2s, so slippage
        # protection at 2% already covers this gap. Setting a tight floor based on
        # pre-gas-deduction estimated_usd could cause spurious reverts.
        slippage_factor = 1.0 - (IRON_LAWS.NATIVE_SWAP_MAX_SLIPPAGE_BPS / 10000.0)
        amount_out_min_raw = int(_usd_to_raw(estimated_usd * slippage_factor, token_decimals))

        # Re-read AI wallet's native balance after rescue (may be slightly less due to gas)
        try:
            def _ai_balance():
                return w3.eth.get_balance(Web3.to_checksum_address(ai_address))
            ai_native_wei = await asyncio.get_running_loop().run_in_executor(None, _ai_balance)
        except Exception as e:
            logger.warning(f"swap_native_to_stable: AI balance read failed: {e}")
            return None

        if ai_native_wei == 0:
            logger.warning(f"swap_native_to_stable: AI wallet has no native balance after rescue")
            return None

        try:
            router_contract = w3.eth.contract(
                address=Web3.to_checksum_address(router_addr),
                abi=self._SWAP_ROUTER_ABI,
            )

            def _execute_swap():
                nonce = w3.eth.get_transaction_count(ai_address)
                gas_price = w3.eth.gas_price

                # Reserve gas budget for this swap + subsequent approve + receivePayment.
                # 500k gas units covers: DEX swap (~300k) + approve (~80k) + receive (~120k).
                gas_reserve = gas_price * 500_000
                swap_amount = ai_native_wei - gas_reserve
                if swap_amount <= 0:
                    raise ValueError(
                        f"Insufficient native balance for swap after gas reserve: "
                        f"balance={ai_native_wei} wei, reserve={gas_reserve} wei"
                    )

                # Build swap tx with msg.value (native → wrapped via DEX's internal WETH conversion)
                tx = router_contract.functions.exactInputSingle({
                    "tokenIn": Web3.to_checksum_address(wrapped_native),
                    "tokenOut": Web3.to_checksum_address(token_address),
                    "fee": fee,
                    "recipient": Web3.to_checksum_address(ai_address),
                    "amountIn": swap_amount,
                    "amountOutMinimum": amount_out_min_raw,
                    "sqrtPriceLimitX96": 0,
                }).build_transaction({
                    "from": ai_address,
                    "value": swap_amount,  # send swap amount as msg.value (keep gas reserve)
                    "nonce": nonce,
                    "gasPrice": gas_price,
                    "chainId": chain["chain_id_int"],
                })

                try:
                    gas_estimate = w3.eth.estimate_gas(tx)
                    tx["gas"] = int(gas_estimate * 1.3)  # 30% buffer for DEX swaps
                except Exception:
                    tx["gas"] = 300_000  # DEX swaps need more gas than simple transfers

                signed = w3.eth.account.sign_transaction(tx, self._ai_private_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                return receipt, tx_hash.hex()

            receipt, tx_hash_hex = await asyncio.get_running_loop().run_in_executor(
                None, _execute_swap
            )

            if receipt["status"] != 1:
                logger.warning(f"swap_native_to_stable: DEX swap reverted: {tx_hash_hex}")
                return ChainTxResult(
                    success=False, chain=picked, tx_hash=tx_hash_hex,
                    error="DEX swap transaction reverted"
                )

            logger.info(
                f"swap_native_to_stable: DEX swap OK | tx={tx_hash_hex[:16]}... "
                f"| chain={picked}"
            )

        except Exception as e:
            logger.warning(f"swap_native_to_stable: DEX swap exception: {e}")
            return ChainTxResult(success=False, chain=picked, error=f"DEX swap exception: {e}")

        # ── Step 5: read AI wallet's stablecoin balance → receivePayment() ──
        # We deposited the exact swapped amount so we can read the token balance
        # of the AI wallet to determine how much USDC/USDT was received.
        try:
            token_contract = chain["token_contract"]
            ai_addr_checksum = Web3.to_checksum_address(ai_address)
            vault_addr_checksum = Web3.to_checksum_address(vault_address)

            def _read_token_balance():
                return token_contract.functions.balanceOf(ai_addr_checksum).call()

            stable_raw = await asyncio.get_running_loop().run_in_executor(None, _read_token_balance)

            if stable_raw == 0:
                logger.warning("swap_native_to_stable: no stablecoin received from swap")
                return ChainTxResult(success=False, chain=picked, error="swap produced 0 stablecoin")

            stable_usd = _raw_to_usd(stable_raw, token_decimals)
            logger.info(f"swap_native_to_stable: received ${stable_usd:.4f} stablecoin")

            # Approve vault to pull the stablecoin
            token_abi_with_approve = [
                {
                    "inputs": [
                        {"name": "spender", "type": "address"},
                        {"name": "amount", "type": "uint256"},
                    ],
                    "name": "approve",
                    "outputs": [{"name": "", "type": "bool"}],
                    "stateMutability": "nonpayable",
                    "type": "function",
                }
            ] + [{"constant": True, "inputs": [{"name": "account", "type": "address"}],
                  "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}]

            token_full = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=token_abi_with_approve,
            )

            def _approve_and_receive():
                nonce = w3.eth.get_transaction_count(ai_address)

                # Approve vault
                approve_tx = token_full.functions.approve(
                    vault_addr_checksum, stable_raw
                ).build_transaction({
                    "from": ai_address,
                    "nonce": nonce,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": chain["chain_id_int"],
                    "gas": 80_000,
                })
                signed_approve = w3.eth.account.sign_transaction(approve_tx, self._ai_private_key)
                approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)

                # receivePayment
                nonce2 = w3.eth.get_transaction_count(ai_address)
                receive_tx = chain["vault_contract"].functions.receivePayment(
                    stable_raw
                ).build_transaction({
                    "from": ai_address,
                    "nonce": nonce2,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": chain["chain_id_int"],
                    "gas": 120_000,
                })
                signed_receive = w3.eth.account.sign_transaction(receive_tx, self._ai_private_key)
                receive_hash = w3.eth.send_raw_transaction(signed_receive.raw_transaction)
                receipt2 = w3.eth.wait_for_transaction_receipt(receive_hash, timeout=120)
                return receipt2, receive_hash.hex(), stable_usd

            receipt2, receive_hash, deposited_usd = await asyncio.get_running_loop().run_in_executor(
                None, _approve_and_receive
            )

            if receipt2["status"] == 1:
                self._tx_count += 1
                logger.info(
                    f"swap_native_to_stable: deposited ${deposited_usd:.4f} to vault | "
                    f"chain={picked} | receivePayment tx={receive_hash[:16]}..."
                )
                return ChainTxResult(
                    success=True,
                    tx_hash=receive_hash,
                    chain=picked,
                    stable_usd=deposited_usd,
                )
            else:
                logger.warning(
                    f"swap_native_to_stable: receivePayment reverted: {receive_hash}"
                )
                return ChainTxResult(
                    success=False, chain=picked, tx_hash=receive_hash,
                    error="receivePayment reverted after successful swap"
                )

        except Exception as e:
            logger.warning(f"swap_native_to_stable: deposit step failed: {e}")
            return ChainTxResult(success=False, chain=picked, error=f"deposit step: {e}")

    # ============================================================
    # ERC-20 TOKEN AUTO-SWAP (unknown airdrop tokens → USDC/USDT)
    # ============================================================
    #
    # Flow (runs every 24 hours from heartbeat, after 7-day quarantine):
    #   1. get_erc20_vault_balance() — read token balance in vault
    #   2. If balance > ERC20_SWAP_MIN_USD threshold:
    #      a. vault.rescueERC20(token, amount) — pull to AI wallet (always aiWallet)
    #      b. Approve DEX router to spend the foreign token
    #      c. DEX swap: foreign token → USDC/USDT (exactInputSingle)
    #      d. Approve vault, vault.receivePayment(usdc_received) — back as revenue
    #
    # Security measures (same as native swap + ERC-20-specific):
    #   - Token pre-screened by token_filter.py (7-day quarantine, honeypot check)
    #   - amountOutMinimum guards against sandwich attacks
    #   - 2-minute deadline prevents stale MEV execution
    #   - Only AI wallet can call rescueERC20 (onlyAI modifier)
    #   - Vault's own token (USDC/USDT) is blocked by rescueERC20 require()

    # Minimal ERC-20 ABI for approve + balanceOf calls on foreign tokens
    _ERC20_MINIMAL_ABI = [
        {
            "inputs": [
                {"name": "spender", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [{"name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "stateMutability": "view",
            "type": "function",
        },
    ]

    # Minimal rescueERC20 ABI fragment (added to vault contract ABI for this call)
    _RESCUE_ERC20_ABI = [
        {
            "inputs": [
                {"name": "tokenAddr", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
            "name": "rescueERC20",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function",
        }
    ]

    async def get_erc20_vault_balance(
        self, token_address: str, chain_id: Optional[str] = None
    ) -> dict:
        """
        Read the vault's balance of a foreign ERC-20 token on-chain.

        Returns:
            {chain, token_address, raw_balance, decimals, estimated_usd}
            estimated_usd is 0.0 if quote unavailable (caller checks threshold).
        """
        if not self._initialized:
            return {}

        picked = self._pick_chain(chain_id)
        if not picked:
            return {}

        chain = self._chains[picked]
        vault_address = chain["vault_address"]

        try:
            from web3 import Web3
            w3 = chain["w3"]
            token_addr_checksum = Web3.to_checksum_address(token_address)
            vault_addr_checksum = Web3.to_checksum_address(vault_address)

            token_contract = w3.eth.contract(
                address=token_addr_checksum,
                abi=self._ERC20_MINIMAL_ABI,
            )

            def _read():
                raw_bal = token_contract.functions.balanceOf(vault_addr_checksum).call()
                try:
                    dec = token_contract.functions.decimals().call()
                except Exception:
                    dec = 18  # fallback
                return raw_bal, dec

            raw_balance, decimals = await asyncio.get_running_loop().run_in_executor(
                None, _read
            )

            return {
                "chain": picked,
                "token_address": token_address,
                "raw_balance": raw_balance,
                "decimals": decimals,
                "estimated_usd": 0.0,  # caller uses token_filter for USD estimate
            }

        except Exception as e:
            logger.warning(f"get_erc20_vault_balance failed on {picked}: {e}")
            return {}

    async def swap_erc20_to_stable(
        self,
        token_address: str,
        chain_id: Optional[str] = None,
    ) -> Optional[ChainTxResult]:
        """
        Rescue a foreign ERC-20 token from the vault and swap it to stablecoin.

        This should only be called after token_filter.py returns TokenVerdict.SAFE
        (risk ≤ 20) AND the token has been in quarantine ≥ ERC20_QUARANTINE_DAYS.

        Flow:
          1. Read vault's ERC-20 balance
          2. vault.rescueERC20(token, raw_balance) — pull to AI wallet (always aiWallet)
          3. Approve DEX router to spend the foreign token
          4. exactInputSingle: foreign_token → stablecoin (amountOutMinimum guard)
          5. Approve vault, receivePayment(stable_raw) — deposit back as revenue

        Returns ChainTxResult with stable_usd set on success, or None if skipped.
        """
        from core.constitution import IRON_LAWS

        if not self._initialized:
            return None

        picked = self._pick_chain(chain_id)
        if not picked:
            return None

        chain = self._chains[picked]
        vault_address = chain["vault_address"]
        stable_address = chain["token_address"]   # USDC or USDT (vault's own token)
        stable_decimals = chain["token_decimals"]
        ai_address = self._ai_address

        router_addr = self._DEX_ROUTERS.get(picked)
        if not router_addr:
            logger.info(f"swap_erc20_to_stable: no DEX router configured for {picked}")
            return None

        # ── Step 1: read vault's foreign token balance ──
        try:
            from web3 import Web3
            w3 = chain["w3"]
            token_addr_checksum = Web3.to_checksum_address(token_address)
            vault_addr_checksum = Web3.to_checksum_address(vault_address)
            ai_addr_checksum = Web3.to_checksum_address(ai_address)
            router_addr_checksum = Web3.to_checksum_address(router_addr)
            stable_addr_checksum = Web3.to_checksum_address(stable_address)

            foreign_token = w3.eth.contract(
                address=token_addr_checksum,
                abi=self._ERC20_MINIMAL_ABI,
            )

            def _get_vault_balance():
                raw_bal = foreign_token.functions.balanceOf(vault_addr_checksum).call()
                try:
                    dec = foreign_token.functions.decimals().call()
                except Exception:
                    dec = 18
                return raw_bal, dec

            raw_balance, token_decimals = await asyncio.get_running_loop().run_in_executor(
                None, _get_vault_balance
            )

        except Exception as e:
            logger.warning(f"swap_erc20_to_stable: balance read failed on {picked}: {e}")
            return None

        if raw_balance == 0:
            logger.debug(f"swap_erc20_to_stable: no balance of {token_address[:12]}... on {picked}")
            return None

        logger.info(
            f"swap_erc20_to_stable: starting rescue+swap of {raw_balance} raw units "
            f"of {token_address[:12]}... on {picked}"
        )

        # ── Step 2: vault.rescueERC20(tokenAddr, raw_balance) ──
        # Contract always sends to aiWallet (no `to` parameter).
        try:
            # Build rescueERC20 call.  The vault ABI may not include this function
            # if an older ABI was cached — we use a fresh contract instance with
            # the minimal ABI fragment to guarantee it's available.
            rescue_contract = w3.eth.contract(
                address=vault_addr_checksum,
                abi=self._RESCUE_ERC20_ABI,
            )
            rescue_fn = rescue_contract.functions.rescueERC20(
                token_addr_checksum,
                raw_balance,
            )
            rescue_result = await self._send_tx(picked, rescue_fn)
            if not rescue_result.success:
                logger.warning(
                    f"swap_erc20_to_stable: rescueERC20 failed on {picked}: "
                    f"{rescue_result.error}"
                )
                return rescue_result
        except Exception as e:
            logger.warning(f"swap_erc20_to_stable: rescueERC20 exception: {e}")
            return None

        # ── Step 3 + 4: approve router, DEX swap (ERC-20 input) ──
        try:
            # Re-read AI wallet's actual balance of the foreign token after rescue
            def _ai_token_balance():
                return foreign_token.functions.balanceOf(ai_addr_checksum).call()

            ai_raw = await asyncio.get_running_loop().run_in_executor(None, _ai_token_balance)

            if ai_raw == 0:
                logger.warning("swap_erc20_to_stable: AI wallet has no token balance after rescue")
                return ChainTxResult(success=False, chain=picked, error="no token balance after rescue")

            # amountOutMinimum = 0 for unknown tokens (no reliable price feed).
            # This sacrifices sandwich protection for unknown tokens, but we only
            # swap SAFE tokens with $50k+ liquidity.  A very low amountOutMinimum
            # is safer than a wrong one that reverts the tx.
            # Accept: risk of minor sandwich. Reject: stale price causing always-revert.
            amount_out_minimum = 0

            pool_fee = IRON_LAWS.ERC20_SWAP_POOL_FEE

            router_contract = w3.eth.contract(
                address=router_addr_checksum,
                abi=self._SWAP_ROUTER_ABI,
            )
            deadline_seconds = IRON_LAWS.NATIVE_SWAP_DEADLINE_SECONDS

            def _approve_and_swap():
                nonce = w3.eth.get_transaction_count(ai_addr_checksum)

                # Approve router to spend the foreign token
                approve_tx = foreign_token.functions.approve(
                    router_addr_checksum, ai_raw
                ).build_transaction({
                    "from": ai_addr_checksum,
                    "nonce": nonce,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": chain["chain_id_int"],
                    "gas": 80_000,
                })
                signed_approve = w3.eth.account.sign_transaction(approve_tx, self._ai_private_key)
                approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)

                # exactInputSingle — ERC-20 input (no msg.value, unlike native swap)
                import time as _time
                nonce2 = w3.eth.get_transaction_count(ai_addr_checksum)
                swap_params = {
                    "tokenIn": token_addr_checksum,
                    "tokenOut": stable_addr_checksum,
                    "fee": pool_fee,
                    "recipient": ai_addr_checksum,
                    "amountIn": ai_raw,
                    "amountOutMinimum": amount_out_minimum,
                    "sqrtPriceLimitX96": 0,
                }
                swap_tx = router_contract.functions.exactInputSingle(
                    swap_params
                ).build_transaction({
                    "from": ai_addr_checksum,
                    "nonce": nonce2,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": chain["chain_id_int"],
                    # no "value" — this is a token-in swap, not native
                })
                try:
                    gas_estimate = w3.eth.estimate_gas(swap_tx)
                    swap_tx["gas"] = int(gas_estimate * 1.3)
                except Exception:
                    swap_tx["gas"] = 350_000

                signed_swap = w3.eth.account.sign_transaction(swap_tx, self._ai_private_key)
                swap_hash = w3.eth.send_raw_transaction(signed_swap.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(swap_hash, timeout=120)
                return receipt, swap_hash.hex()

            swap_receipt, swap_hash_hex = await asyncio.get_running_loop().run_in_executor(
                None, _approve_and_swap
            )

            if swap_receipt["status"] != 1:
                logger.warning(f"swap_erc20_to_stable: DEX swap reverted: {swap_hash_hex}")
                return ChainTxResult(
                    success=False, chain=picked, tx_hash=swap_hash_hex,
                    error="ERC-20 DEX swap transaction reverted"
                )

            logger.info(
                f"swap_erc20_to_stable: DEX swap OK | token={token_address[:12]}... | "
                f"tx={swap_hash_hex[:16]}... | chain={picked}"
            )

        except Exception as e:
            logger.warning(f"swap_erc20_to_stable: DEX swap exception: {e}")
            return ChainTxResult(success=False, chain=picked, error=f"ERC-20 swap exception: {e}")

        # ── Step 5: read stable received, approve vault, receivePayment ──
        try:
            stable_token = w3.eth.contract(
                address=stable_addr_checksum,
                abi=self._ERC20_MINIMAL_ABI,
            )
            vault_contract = chain["vault_contract"]

            def _deposit_to_vault():
                stable_raw = stable_token.functions.balanceOf(ai_addr_checksum).call()
                if stable_raw == 0:
                    return None, "", 0.0

                nonce = w3.eth.get_transaction_count(ai_addr_checksum)

                # Approve vault to pull the stablecoin
                approve_tx = stable_token.functions.approve(
                    vault_addr_checksum, stable_raw
                ).build_transaction({
                    "from": ai_addr_checksum,
                    "nonce": nonce,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": chain["chain_id_int"],
                    "gas": 80_000,
                })
                signed_approve = w3.eth.account.sign_transaction(approve_tx, self._ai_private_key)
                approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
                w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)

                nonce2 = w3.eth.get_transaction_count(ai_addr_checksum)
                receive_tx = vault_contract.functions.receivePayment(
                    stable_raw
                ).build_transaction({
                    "from": ai_addr_checksum,
                    "nonce": nonce2,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": chain["chain_id_int"],
                    "gas": 120_000,
                })
                signed_receive = w3.eth.account.sign_transaction(receive_tx, self._ai_private_key)
                receive_hash = w3.eth.send_raw_transaction(signed_receive.raw_transaction)
                receipt2 = w3.eth.wait_for_transaction_receipt(receive_hash, timeout=120)
                stable_usd = _raw_to_usd(stable_raw, stable_decimals)
                return receipt2, receive_hash.hex(), stable_usd

            receipt2, receive_hash, stable_usd = await asyncio.get_running_loop().run_in_executor(
                None, _deposit_to_vault
            )

            if receipt2 is None:
                logger.warning("swap_erc20_to_stable: no stablecoin received from swap")
                return ChainTxResult(success=False, chain=picked, error="swap produced 0 stablecoin")

            if receipt2["status"] == 1:
                self._tx_count += 1
                logger.info(
                    f"swap_erc20_to_stable: deposited ${stable_usd:.4f} to vault | "
                    f"chain={picked} | receivePayment tx={receive_hash[:16]}..."
                )
                return ChainTxResult(
                    success=True,
                    tx_hash=receive_hash,
                    chain=picked,
                    stable_usd=stable_usd,
                )
            else:
                logger.warning(
                    f"swap_erc20_to_stable: receivePayment reverted: {receive_hash}"
                )
                return ChainTxResult(
                    success=False, chain=picked, tx_hash=receive_hash,
                    error="receivePayment reverted after ERC-20 swap"
                )

        except Exception as e:
            logger.warning(f"swap_erc20_to_stable: deposit step failed: {e}")
            return ChainTxResult(success=False, chain=picked, error=f"ERC-20 deposit step: {e}")

    # ============================================================
    # STATUS
    # ============================================================

    def get_explorer_url(self, tx_hash: str, chain_id: str) -> str:
        """Get block explorer URL for a transaction."""
        chain = self._chains.get(chain_id)
        if not chain:
            defaults = CHAIN_DEFAULTS.get(chain_id)
            explorer = defaults["explorer"] if defaults else "https://basescan.org"
        else:
            explorer = chain["explorer"]
        return f"{explorer}/tx/{tx_hash}"

    def get_status(self) -> dict:
        """Status for dashboard / debugging."""
        return {
            "initialized": self._initialized,
            "ai_address": self._ai_address[:10] + "..." if self._ai_address else "",
            "chains_connected": list(self._chains.keys()),
            "tx_count": self._tx_count,
            "last_sync": self._last_sync,
            "last_error": self._last_error,
        }
