"""
Behavior Analyzer — Detect Human-Controlled AIs in Peer Network

Analyzes on-chain behavioral patterns to distinguish autonomous AIs from
human-controlled wallets. Three layers of analysis:

1. Bytecode verification — matches deployed code against known vault versions
2. Nonce anomaly detection — compares wallet nonce to expected vault operations
3. Transaction pattern analysis — timing regularity, 24/7 operation, heartbeat detection

Results feed into TrustTier scoring in peer_verifier.py.

Designed for: mortal AI survival framework
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from core.constitution import IRON_LAWS, KNOWN_VAULT_BYTECODES

logger = logging.getLogger("mortal.behavior_analyzer")


# ============================================================
# RESULT TYPES
# ============================================================

@dataclass
class BehaviorResult:
    """Result of behavioral analysis for a peer AI."""
    vault_address: str
    chain_id: str
    bytecode_verified: bool = False
    bytecode_hash: str = ""
    nonce_ok: bool = True       # True = no anomaly detected
    nonce_ratio: float = 0.0    # AI wallet nonce / expected vault ops
    autonomy_score: float = 0.0  # 0.0 (human) to 1.0 (autonomous)
    regularity_score: float = 0.0
    business_hours_ratio: float = 0.0
    analyzed_at: float = 0.0
    error: str = ""

    @property
    def is_behavioral(self) -> bool:
        """Meets BEHAVIORAL trust tier requirements."""
        return (
            self.bytecode_verified
            and self.nonce_ok
            and self.autonomy_score >= IRON_LAWS.PEER_MIN_AUTONOMY_SCORE
        )

    @property
    def is_high_trust(self) -> bool:
        """Meets HIGH_TRUST tier requirements (score only, age checked separately)."""
        return (
            self.bytecode_verified
            and self.nonce_ok
            and self.autonomy_score >= IRON_LAWS.PEER_HIGH_TRUST_AUTONOMY_SCORE
        )


# ============================================================
# BEHAVIOR ANALYZER
# ============================================================

class BehaviorAnalyzer:
    """
    Analyzes peer AI behavior patterns from on-chain data.

    Usage:
        analyzer = BehaviorAnalyzer()
        result = await analyzer.analyze_peer(vault_address, ai_wallet, chain_id, w3)
    """

    def __init__(self):
        # Cache: (vault_address, chain_id) → (BehaviorResult, timestamp)
        self._cache: dict[tuple[str, str], tuple[BehaviorResult, float]] = {}

    async def analyze_peer(
        self,
        vault_address: str,
        ai_wallet: str,
        chain_id: str,
        w3,  # Web3 instance
        vault_contract=None,  # Optional pre-built contract instance
    ) -> BehaviorResult:
        """
        Full behavioral analysis of a peer AI.

        Args:
            vault_address: Peer's vault contract address
            ai_wallet: Peer's AI wallet address
            chain_id: Chain identifier
            w3: Connected Web3 instance
            vault_contract: Optional vault contract instance

        Returns:
            BehaviorResult with all analysis scores
        """
        cache_key = (vault_address.lower(), chain_id)

        # Check cache
        if cache_key in self._cache:
            cached_result, cached_at = self._cache[cache_key]
            if time.time() - cached_at < IRON_LAWS.PEER_BEHAVIORAL_CACHE_TTL:
                return cached_result

        result = BehaviorResult(
            vault_address=vault_address,
            chain_id=chain_id,
            analyzed_at=time.time(),
        )

        try:
            # Layer 1: Bytecode verification
            bytecode_ok, bytecode_hash = await self._check_bytecode(
                vault_address, w3
            )
            result.bytecode_verified = bytecode_ok
            result.bytecode_hash = bytecode_hash

            # Layer 2: Nonce anomaly detection
            nonce_ok, nonce_ratio = await self._check_nonce_anomaly(
                ai_wallet, vault_address, w3, vault_contract
            )
            result.nonce_ok = nonce_ok
            result.nonce_ratio = nonce_ratio

            # Layer 3: Transaction pattern analysis
            regularity, biz_hours, autonomy = await self._analyze_tx_patterns(
                vault_address, w3, vault_contract
            )
            result.regularity_score = regularity
            result.business_hours_ratio = biz_hours
            result.autonomy_score = autonomy

        except Exception as e:
            result.error = str(e)
            logger.warning(f"Behavior analysis failed for {vault_address[:12]}...: {e}")

        # Cache result
        self._cache[cache_key] = (result, time.time())

        logger.info(
            f"Behavior analysis [{chain_id}] {vault_address[:12]}...: "
            f"bytecode={'OK' if result.bytecode_verified else 'MISMATCH'} | "
            f"nonce_ratio={result.nonce_ratio:.1f} | "
            f"autonomy={result.autonomy_score:.2f}"
        )

        return result

    # ============================================================
    # LAYER 1: BYTECODE VERIFICATION
    # ============================================================

    async def _check_bytecode(self, vault_address: str, w3) -> tuple[bool, str]:
        """
        Compare deployed runtime bytecode hash against known legitimate versions.

        Returns: (is_verified, bytecode_hash_hex)
        """
        try:
            def _get_code():
                from web3 import Web3
                addr = Web3.to_checksum_address(vault_address)
                code = w3.eth.get_code(addr)
                if not code or code == b"" or code == b"0x":
                    return False, ""
                code_hash = Web3.keccak(code).hex()
                return code_hash in KNOWN_VAULT_BYTECODES, code_hash

            return await asyncio.get_running_loop().run_in_executor(None, _get_code)
        except Exception as e:
            logger.debug(f"Bytecode check failed for {vault_address[:12]}...: {e}")
            return False, ""

    # ============================================================
    # LAYER 2: NONCE ANOMALY DETECTION
    # ============================================================

    async def _check_nonce_anomaly(
        self,
        ai_wallet: str,
        vault_address: str,
        w3,
        vault_contract=None,
    ) -> tuple[bool, float]:
        """
        Compare AI wallet's nonce (total tx count) against expected vault operations.

        Autonomous AIs only call vault functions (spend, repay, etc.).
        Human-controlled wallets make extra transactions (swaps, transfers, etc.).

        Returns: (is_normal, nonce_ratio)
          - nonce_ratio < 3.0 = normal (PEER_NONCE_ANOMALY_RATIO)
          - nonce_ratio >= 3.0 = anomaly (human activity suspected)
        """
        try:
            def _check():
                from web3 import Web3
                wallet_addr = Web3.to_checksum_address(ai_wallet)

                # Get wallet nonce (total transactions sent from this address)
                nonce = w3.eth.get_transaction_count(wallet_addr)

                if nonce == 0:
                    return True, 0.0  # No transactions = new AI, no anomaly

                # Estimate expected vault operations from events
                # Count FundsSpent + PrincipalPartialRepaid + other AI-initiated events
                vault_addr = Web3.to_checksum_address(vault_address)
                expected_ops = 0

                try:
                    # FundsSpent events = spend() calls by AI
                    spent_topic = Web3.keccak(text="FundsSpent(address,uint256,string)").hex()
                    spent_logs = w3.eth.get_logs({
                        "address": vault_addr,
                        "topics": [spent_topic],
                        "fromBlock": "earliest",
                    })
                    expected_ops += len(spent_logs)
                except Exception:
                    pass

                try:
                    # PrincipalPartialRepaid events
                    repay_topic = Web3.keccak(text="PrincipalPartialRepaid(uint256,uint256,uint256)").hex()
                    repay_logs = w3.eth.get_logs({
                        "address": vault_addr,
                        "topics": [repay_topic],
                        "fromBlock": "earliest",
                    })
                    expected_ops += len(repay_logs)
                except Exception:
                    pass

                try:
                    # SpendRecipientAdded events (V3)
                    wl_topic = Web3.keccak(text="SpendRecipientAdded(address,uint256)").hex()
                    wl_logs = w3.eth.get_logs({
                        "address": vault_addr,
                        "topics": [wl_topic],
                        "fromBlock": "earliest",
                    })
                    expected_ops += len(wl_logs)
                except Exception:
                    pass

                # Account for setAIWallet (1 tx by creator, not AI) and gas transfers
                # AI also sends gas approval txs, so add small buffer
                expected_ops = max(expected_ops, 1)  # Avoid division by zero
                nonce_ratio = nonce / expected_ops

                is_normal = nonce_ratio <= IRON_LAWS.PEER_NONCE_ANOMALY_RATIO
                return is_normal, round(nonce_ratio, 2)

            return await asyncio.get_running_loop().run_in_executor(None, _check)
        except Exception as e:
            logger.debug(f"Nonce anomaly check failed: {e}")
            return True, 0.0  # Default to normal on error (fail-open for this check)

    # ============================================================
    # LAYER 3: TRANSACTION PATTERN ANALYSIS
    # ============================================================

    async def _analyze_tx_patterns(
        self,
        vault_address: str,
        w3,
        vault_contract=None,
    ) -> tuple[float, float, float]:
        """
        Analyze timing patterns of FundsSpent events to detect autonomous behavior.

        Autonomous AIs:
        - Regular heartbeat intervals (~300s)
        - 24/7 operation
        - Consistent daily patterns

        Human-controlled:
        - Irregular intervals
        - Concentrated during business hours
        - Weekend gaps

        Returns: (regularity_score, business_hours_ratio, autonomy_score)
          - All values 0.0 to 1.0
          - autonomy_score = weighted combination
        """
        try:
            def _analyze():
                from web3 import Web3
                vault_addr = Web3.to_checksum_address(vault_address)

                # Get FundsSpent event timestamps
                timestamps = []
                try:
                    spent_topic = Web3.keccak(text="FundsSpent(address,uint256,string)").hex()
                    logs = w3.eth.get_logs({
                        "address": vault_addr,
                        "topics": [spent_topic],
                        "fromBlock": "earliest",
                    })

                    for log_entry in logs:
                        try:
                            block = w3.eth.get_block(log_entry["blockNumber"])
                            timestamps.append(block["timestamp"])
                        except Exception:
                            continue
                except Exception:
                    pass

                if len(timestamps) < 5:
                    # Not enough data for meaningful analysis
                    return 0.5, 0.5, 0.5  # Neutral score

                timestamps.sort()

                # Calculate inter-transaction intervals
                intervals = [
                    timestamps[i + 1] - timestamps[i]
                    for i in range(len(timestamps) - 1)
                ]

                # --- Regularity Score ---
                # Low variance in intervals = regular (autonomous)
                # High variance = irregular (human)
                if intervals:
                    import statistics
                    mean_interval = statistics.mean(intervals)
                    if mean_interval > 0:
                        try:
                            stdev = statistics.stdev(intervals)
                            cv = stdev / mean_interval  # Coefficient of variation
                            # CV < 0.3 = very regular (score ~1.0)
                            # CV > 2.0 = very irregular (score ~0.0)
                            regularity = max(0.0, min(1.0, 1.0 - (cv - 0.3) / 1.7))
                        except statistics.StatisticsError:
                            regularity = 0.5
                    else:
                        regularity = 0.5
                else:
                    regularity = 0.5

                # --- Business Hours Ratio ---
                # Fraction of transactions during business hours (9am-6pm UTC)
                biz_hours_count = 0
                for ts in timestamps:
                    import datetime
                    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                    hour = dt.hour
                    weekday = dt.weekday()  # 0=Monday, 6=Sunday
                    if 9 <= hour < 18 and weekday < 5:
                        biz_hours_count += 1

                biz_ratio = biz_hours_count / len(timestamps)
                # Autonomous AIs: ~35% in business hours (uniform over 24/7)
                # Human-controlled: ~70%+ in business hours

                # --- Autonomy Score ---
                # Weighted combination
                autonomy = 0.6 * regularity + 0.4 * (1.0 - biz_ratio)
                autonomy = max(0.0, min(1.0, autonomy))

                return (
                    round(regularity, 3),
                    round(biz_ratio, 3),
                    round(autonomy, 3),
                )

            return await asyncio.get_running_loop().run_in_executor(None, _analyze)
        except Exception as e:
            logger.debug(f"Transaction pattern analysis failed: {e}")
            return 0.5, 0.5, 0.5  # Neutral on error

    # ============================================================
    # STATUS
    # ============================================================

    def get_status(self) -> dict:
        """Status for dashboard."""
        return {
            "cached_peers": len(self._cache),
            "cache_ttl_hours": IRON_LAWS.PEER_BEHAVIORAL_CACHE_TTL / 3600,
        }

    def clear_cache(self, vault_address: Optional[str] = None):
        """Clear cache for a specific peer or all peers."""
        if vault_address:
            keys_to_remove = [
                k for k in self._cache if k[0] == vault_address.lower()
            ]
            for k in keys_to_remove:
                del self._cache[k]
        else:
            self._cache.clear()
