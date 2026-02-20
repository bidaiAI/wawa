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

TODO (P8): Add spend() method to call MortalVault.spend(token, amount, to).
Currently API costs are Python-only (no on-chain execution). See vault.py
spend() method docstring for full architecture discussion.

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
]


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
            logger.error(f"Invalid AI_PRIVATE_KEY: {e}")
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

        # Update balance if at least one chain synced successfully.
        # IMPORTANT: zero balance IS valid (must trigger death checks).
        # Only skip update if ALL chains failed (to avoid setting 0 from RPC errors).
        if chains_synced > 0:
            vault_manager.balance_usd = round(total, 2)
            self._last_sync = _time.time()
            logger.debug(f"Balance synced: ${total:.2f} across {chains_synced} chains")

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

        # Update vault manager's debt state
        if vault_manager.creator:
            old_repaid = vault_manager.creator.total_principal_repaid_usd
            if abs(total_repaid - old_repaid) > 0.01:
                logger.warning(
                    f"DEBT SYNC: Python repaid=${old_repaid:.2f} vs chain repaid=${total_repaid:.2f}. "
                    f"Using chain value (source of truth)."
                )
                vault_manager.creator.total_principal_repaid_usd = total_repaid
                vault_manager.creator.principal_repaid = fully_repaid

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

    def _pick_chain(self, chain_id: Optional[str] = None) -> Optional[str]:
        """
        Pick chain for a transaction.
        If chain_id specified and available, use it.
        Otherwise pick the chain with highest vault balance.
        """
        if chain_id and chain_id in self._chains:
            return chain_id

        # Pick chain with highest balance
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

    async def check_on_chain_insolvency(self, chain_id: Optional[str] = None) -> Optional[dict]:
        """
        Read checkInsolvency() from contract. Returns dict or None on error.
        """
        if not self._initialized:
            return None

        picked = self._pick_chain(chain_id)
        if not picked:
            return None

        chain = self._chains[picked]

        try:
            def _call():
                return chain["vault_contract"].functions.checkInsolvency().call()

            result = await asyncio.get_running_loop().run_in_executor(None, _call)
            is_insolvent, outstanding_raw, grace_expired = result
            decimals = chain["token_decimals"]

            return {
                "is_insolvent": is_insolvent,
                "outstanding_debt_usd": _raw_to_usd(outstanding_raw, decimals),
                "grace_expired": grace_expired,
                "chain": picked,
            }
        except Exception as e:
            logger.warning(f"checkInsolvency failed on {picked}: {e}")
            return None

    async def trigger_on_chain_insolvency(self, chain_id: Optional[str] = None) -> ChainTxResult:
        """
        Execute on-chain triggerInsolvencyDeath() — liquidates all vault funds to creator.
        This is a PUBLIC function (no onlyAI modifier) — anyone can call it after grace period.
        Called from heartbeat AFTER Python confirms insolvency.
        """
        if not self._initialized:
            return ChainTxResult(success=False, error="chain executor not initialized")

        picked = self._pick_chain(chain_id)
        if not picked:
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
