"""
Peer Sovereignty Verifier — V3 with Behavioral Analysis

Verifies that a peer AI's vault is a genuine autonomous MortalVault,
where no human controls the AI private key and the contract constitution
is unmodified (28-day grace period, aiWallet != creator, etc.)

V3 adds behavioral analysis to detect human-controlled AIs:
- Bytecode verification (CHECK 8)
- Nonce anomaly detection (CHECK 9)
- Transaction pattern analysis (CHECK 10)
- Graduated TrustTier system (replaces binary is_sovereign)

Design principles:
- Fail-closed: any RPC failure -> reject. Do not trust unverified peers.
- Dual-chain: works for both Base (USDC) and BSC (USDT).
- Cached: verified peers are trusted for PEER_VERIFICATION_CACHE_TTL seconds.
- Stateless: no external storage. Cache lives only in process memory.
- Reusable: called from API endpoints, also usable by future peer discovery.

10 checks (7 structural + 3 behavioral):
  1. aiWallet != address(0) -- sovereignty moment completed
  2. creator != address(0) -- valid deployment
  3. aiWallet != creator -- AI cannot be controlled by creator
  4. isAlive == true -- contract is alive
  5. graceDays == 28 -- genuine constitution (unmodified insolvency rules)
  6. balance >= $300 -- meets peer network threshold (on-chain, not self-reported)
  7. deployment_method valid -- aiWalletSetBy matches factory/creator/migrated
  8. bytecode verified -- matches known MortalVault versions (V3)
  9. nonce normal -- AI wallet nonce consistent with vault operations (V3)
 10. autonomy score -- transaction timing patterns indicate autonomous behavior (V3)

Designed for: mortal AI survival framework
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from .chain import CHAIN_DEFAULTS, VAULT_ABI, ERC20_ABI, _raw_to_usd
from .constitution import IRON_LAWS, TrustTier
from .behavior_analyzer import BehaviorAnalyzer, BehaviorResult

logger = logging.getLogger("mortal.peer_verifier")

NULL_ADDRESS = "0x" + "0" * 40

# Strike threshold: how many consecutive "invalid" key_origin detections before permanent ban.
# First detections are warnings (still rejected), giving time for RPC anomalies to clear.
# Once threshold is reached, the peer is banned (cached indefinitely).
INVALID_KEY_ORIGIN_STRIKE_THRESHOLD = 3


@dataclass
class SovereigntyResult:
    """Result of a sovereignty verification attempt."""
    vault_address: str
    chain_id: str
    is_sovereign: bool
    checks_passed: list = field(default_factory=list)
    checks_failed: list = field(default_factory=list)
    balance_usd: float = 0.0
    ai_wallet: str = ""
    creator: str = ""
    ai_name: str = ""
    is_alive: bool = False
    days_alive: int = 0
    deployment_method: str = ""   # "factory" | "creator" | "migrated" | "unknown" | "invalid"
    # Backward compat alias
    key_origin: str = ""          # Same as deployment_method (deprecated name)
    ai_wallet_set_by: str = ""    # raw address that called setAIWallet
    factory_address: str = ""     # factory address (V2 only, "" for V1)
    error: str = ""
    verified_at: float = 0.0
    strikes: int = 0              # consecutive invalid deployment_method detections
    banned: bool = False           # True after strikes >= threshold
    # V3: Behavioral analysis
    trust_tier: TrustTier = TrustTier.UNVERIFIED
    bytecode_verified: bool = False
    bytecode_hash: str = ""
    autonomy_score: float = 0.0
    nonce_ratio: float = 0.0


class PeerVerifier:
    """
    Verifies peer AI sovereignty on-chain.

    Usage:
        verifier = PeerVerifier()
        result = await verifier.verify("0xVaultAddress", "base")
        if result.is_sovereign:
            # allow peer interaction
    """

    def __init__(self):
        self._cache: dict[tuple[str, str], SovereigntyResult] = {}
        # Strike counter for invalid deployment_method: (vault, chain) → count
        self._strikes: dict[tuple[str, str], int] = {}
        # Permanently banned peers (strikes >= threshold): never re-check
        self._banned: set[tuple[str, str]] = set()
        # V3: Behavioral analyzer for autonomous AI detection
        self._behavior_analyzer = BehaviorAnalyzer()
        # Peer API URL registry: vault_address.lower() → api_url
        # Populated when peers register or are discovered
        self._peer_api_urls: dict[str, str] = {}

    def _cache_key(self, vault_address: str, chain_id: str) -> tuple[str, str]:
        return (vault_address.lower(), chain_id.lower())

    def _get_cached(self, vault_address: str, chain_id: str) -> Optional[SovereigntyResult]:
        key = self._cache_key(vault_address, chain_id)
        result = self._cache.get(key)
        if result is None:
            return None
        age = time.time() - result.verified_at
        if age > IRON_LAWS.PEER_VERIFICATION_CACHE_TTL:
            del self._cache[key]
            return None
        return result

    def _set_cached(self, result: SovereigntyResult) -> None:
        key = self._cache_key(result.vault_address, result.chain_id)
        self._cache[key] = result

    async def verify(self, vault_address: str, chain_id: str) -> SovereigntyResult:
        """
        Verify peer sovereignty. Returns cached result if fresh.
        Fail-closed: returns is_sovereign=False on any RPC error.

        Caching policy:
        - RPC errors: NOT cached (retry immediately next call to avoid false bans)
        - On-chain failures (invalid key_origin, dead contract, etc.): cached normally
        - Sovereign results: cached normally

        Strike system for invalid key_origin:
        - 1st-2nd detection: WARNING + reject (not banned yet, will re-verify next cycle)
        - 3rd detection: BANNED permanently (cached indefinitely, no more re-checks)
        This avoids false positives from transient RPC data anomalies.
        """
        key = self._cache_key(vault_address, chain_id)

        # Permanent ban check — no further verification needed
        if key in self._banned:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            # Shouldn't happen, but create a banned result just in case
            result = SovereigntyResult(
                vault_address=vault_address, chain_id=chain_id, is_sovereign=False,
                banned=True, strikes=INVALID_KEY_ORIGIN_STRIKE_THRESHOLD,
            )
            result.checks_failed.append("key_origin: BANNED — permanently rejected from peer network")
            result.verified_at = time.time()
            self._cache[key] = result
            return result

        # Cache hit
        cached = self._get_cached(vault_address, chain_id)
        if cached is not None:
            logger.debug(
                f"Sovereignty cache HIT: {vault_address[:16]}... on {chain_id} "
                f"(sovereign={cached.is_sovereign})"
            )
            return cached

        # Cache miss -- full on-chain verification
        result = await self._verify_on_chain(vault_address, chain_id)
        result.verified_at = time.time()

        # Strike system for invalid key_origin
        if result.key_origin == "invalid":
            strikes = self._strikes.get(key, 0) + 1
            self._strikes[key] = strikes
            result.strikes = strikes

            if strikes >= INVALID_KEY_ORIGIN_STRIKE_THRESHOLD:
                # Permanent ban
                result.banned = True
                self._banned.add(key)
                logger.error(
                    f"PEER BANNED: {vault_address[:16]}... on {chain_id} | "
                    f"invalid key_origin confirmed {strikes}x — permanent rejection"
                )
            else:
                # Warning — still rejected but not yet banned
                logger.warning(
                    f"KEY ORIGIN WARNING ({strikes}/{INVALID_KEY_ORIGIN_STRIKE_THRESHOLD}): "
                    f"{vault_address[:16]}... on {chain_id} | "
                    f"invalid key_origin detected — will ban after "
                    f"{INVALID_KEY_ORIGIN_STRIKE_THRESHOLD - strikes} more confirmation(s)"
                )
        else:
            # Valid key_origin — clear any previous strikes
            if key in self._strikes:
                prev = self._strikes.pop(key)
                if prev > 0:
                    logger.info(
                        f"Key origin cleared: {vault_address[:16]}... on {chain_id} | "
                        f"previous {prev} strike(s) reset to 0"
                    )

        # V3: Behavioral analysis (only if structural checks pass)
        if result.is_sovereign and result.ai_wallet and not result.error:
            try:
                behavior = await self._run_behavioral_analysis(
                    vault_address, result.ai_wallet, chain_id
                )
                result.bytecode_verified = behavior.bytecode_verified
                result.bytecode_hash = behavior.bytecode_hash
                result.autonomy_score = behavior.autonomy_score
                result.nonce_ratio = behavior.nonce_ratio

                if not behavior.nonce_ok:
                    result.checks_failed.append(
                        f"nonce_anomaly: ratio={behavior.nonce_ratio:.1f} "
                        f"(threshold={IRON_LAWS.PEER_NONCE_ANOMALY_RATIO})"
                    )
                else:
                    result.checks_passed.append("nonce_normal")

                if behavior.bytecode_verified:
                    result.checks_passed.append("bytecode_verified")
                # Don't fail if bytecode not in known set — just lower trust tier
            except Exception as e:
                logger.debug(f"Behavioral analysis error (non-fatal): {e}")

        # Compute trust tier
        result.trust_tier = self._compute_trust_tier(result)

        # Only cache definitive results — NOT transient RPC errors.
        # RPC errors should be retried next call, not remembered for 1 hour.
        if not result.error:
            self._set_cached(result)

        tier_name = result.trust_tier.name
        status = f"SOVEREIGN/{tier_name}" if result.is_sovereign else ("BANNED" if result.banned else "REJECTED")
        log_fn = logger.info if result.is_sovereign else logger.warning
        log_fn(
            f"Sovereignty check [{status}]: {vault_address[:16]}... on {chain_id} | "
            f"tier={tier_name} | passed={result.checks_passed} | failed={result.checks_failed}"
            + (f" | autonomy={result.autonomy_score:.2f}" if result.autonomy_score > 0 else "")
            + (f" | strikes={result.strikes}" if result.strikes > 0 else "")
            + (f" | error={result.error}" if result.error else "")
        )
        return result

    async def _verify_on_chain(self, vault_address: str, chain_id: str) -> SovereigntyResult:
        """Execute all 7 on-chain sovereignty checks. Never raises -- always returns result."""
        result = SovereigntyResult(
            vault_address=vault_address,
            chain_id=chain_id,
            is_sovereign=False,
        )

        chain_cfg = CHAIN_DEFAULTS.get(chain_id)
        if not chain_cfg:
            result.error = f"Unknown chain: {chain_id}"
            result.checks_failed.append(f"chain_supported: unknown chain '{chain_id}'")
            return result

        try:
            from web3 import Web3
        except ImportError:
            result.error = "web3 not installed"
            result.checks_failed.append("rpc_connect: web3 library not available")
            return result

        try:
            def _run_checks():
                # Connect to RPC (use env override if available, else default)
                rpc_url = os.getenv(
                    f"{chain_id.upper()}_RPC_URL",
                    chain_cfg["rpc"],
                )
                w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
                if not w3.is_connected():
                    raise ConnectionError(f"Cannot connect to {chain_id} RPC: {rpc_url}")

                vault_cs = Web3.to_checksum_address(vault_address)
                vault = w3.eth.contract(address=vault_cs, abi=VAULT_ABI)

                passes = []
                failures = []

                # CHECK 1: aiWallet != address(0) -- sovereignty moment completed
                ai_wallet = vault.functions.aiWallet().call()
                if ai_wallet == NULL_ADDRESS:
                    failures.append("ai_wallet_set: aiWallet is address(0) -- sovereignty never completed")
                else:
                    passes.append("ai_wallet_set")

                # CHECK 2: creator != address(0) -- valid deployment
                creator_addr = vault.functions.creator().call()
                if creator_addr == NULL_ADDRESS:
                    failures.append("creator_valid: creator is address(0) -- malformed contract")
                else:
                    passes.append("creator_valid")

                # CHECK 3: aiWallet != creator -- human cannot control AI key
                if ai_wallet != NULL_ADDRESS and creator_addr != NULL_ADDRESS:
                    if ai_wallet.lower() == creator_addr.lower():
                        failures.append("ai_not_creator: aiWallet == creator -- human controls AI key")
                    else:
                        passes.append("ai_not_creator")

                # CHECK 4: isAlive == true -- contract is alive
                birth_info = vault.functions.getBirthInfo().call()
                birth_name, birth_creator, initial_fund, birth_ts, is_alive, is_independent = birth_info
                if not is_alive:
                    failures.append("is_alive: contract is dead (isAlive == false)")
                else:
                    passes.append("is_alive")

                # CHECK 5: graceDays == 28 -- genuine constitution (unmodified)
                debt_info = vault.functions.getDebtInfo().call()
                (
                    _principal, _repaid, _outstanding,
                    grace_days, _grace_ends_at, _grace_expired, _fully_repaid,
                ) = debt_info
                if grace_days != IRON_LAWS.INSOLVENCY_GRACE_DAYS:
                    failures.append(
                        f"constitution_compliance: graceDays={grace_days} "
                        f"(expected {IRON_LAWS.INSOLVENCY_GRACE_DAYS}) -- modified contract"
                    )
                else:
                    passes.append("constitution_compliance")

                # CHECK 6: on-chain balance >= PEER_MIN_BALANCE_USD
                token_address = Web3.to_checksum_address(chain_cfg["token_address"])
                token = w3.eth.contract(address=token_address, abi=ERC20_ABI)
                balance_raw = token.functions.balanceOf(vault_cs).call()
                decimals = chain_cfg["token_decimals"]
                balance_usd = _raw_to_usd(balance_raw, decimals)

                if balance_usd < IRON_LAWS.PEER_MIN_BALANCE_USD:
                    failures.append(
                        f"min_balance: ${balance_usd:.2f} < "
                        f"${IRON_LAWS.PEER_MIN_BALANCE_USD:.0f} threshold"
                    )
                else:
                    passes.append("min_balance")

                # CHECK 7: key_origin -- who set the AI wallet?
                # Factory-set = key isolated (highest trust).
                # Creator-set = self-hosted (allowed but flagged).
                # Unknown = legacy contract (no aiWalletSetBy, allowed).
                # Invalid = aiWalletSetBy doesn't match factory or creator (BANNED).
                wallet_set_by = NULL_ADDRESS
                factory_addr = NULL_ADDRESS
                key_origin = "unknown"

                try:
                    wallet_set_by = vault.functions.aiWalletSetBy().call()
                except Exception:
                    pass  # Legacy contract without aiWalletSetBy

                try:
                    factory_addr = vault.functions.factory().call()
                except Exception:
                    pass  # V1 contract without factory field

                if wallet_set_by == NULL_ADDRESS:
                    # Legacy contract: no aiWalletSetBy recorded
                    key_origin = "unknown"
                    passes.append("deployment_method: unknown (legacy contract)")
                elif factory_addr != NULL_ADDRESS and wallet_set_by.lower() == factory_addr.lower():
                    # Factory set the key -- platform-hosted, key isolated
                    key_origin = "factory"
                    passes.append("deployment_method: factory (platform-hosted)")
                elif wallet_set_by.lower() == creator_addr.lower():
                    # Creator set the key -- self-hosted
                    key_origin = "creator"
                    passes.append("deployment_method: creator (self-hosted)")
                elif wallet_set_by.lower() == ai_wallet.lower():
                    # AI itself set the key -- migrated (V3 completeMigration sets aiWalletSetBy = newWallet)
                    key_origin = "migrated"
                    passes.append("deployment_method: migrated (AI self-migration)")
                else:
                    # aiWalletSetBy doesn't match any known role -- MODIFIED CONTRACT
                    key_origin = "invalid"
                    failures.append(
                        f"deployment_method: aiWalletSetBy={wallet_set_by[:16]}... "
                        f"matches neither factory, creator, nor AI -- modified contract WARNING"
                    )

                # Calculate days alive
                import time as _time
                days_alive = 0
                if birth_ts > 0:
                    days_alive = int((_time.time() - birth_ts) / 86400)

                return {
                    "ai_wallet": ai_wallet,
                    "creator": creator_addr,
                    "ai_name": birth_name,
                    "is_alive": is_alive,
                    "days_alive": days_alive,
                    "balance_usd": balance_usd,
                    "key_origin": key_origin,
                    "ai_wallet_set_by": wallet_set_by,
                    "factory_address": factory_addr,
                    "passes": passes,
                    "failures": failures,
                }

            data = await asyncio.get_running_loop().run_in_executor(None, _run_checks)

            result.ai_wallet = data["ai_wallet"]
            result.creator = data["creator"]
            result.ai_name = data["ai_name"]
            result.is_alive = data["is_alive"]
            result.days_alive = data.get("days_alive", 0)
            result.balance_usd = data["balance_usd"]
            result.deployment_method = data["key_origin"]
            result.key_origin = data["key_origin"]  # backward compat
            result.ai_wallet_set_by = data["ai_wallet_set_by"]
            result.factory_address = data["factory_address"]
            result.checks_passed = data["passes"]
            result.checks_failed = data["failures"]
            result.is_sovereign = len(data["failures"]) == 0

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            logger.warning(
                f"Sovereignty verification RPC error for "
                f"{vault_address[:16]}...: {error_msg}"
            )
            result.error = error_msg
            result.checks_failed.append(f"rpc_error: {error_msg}")
            result.is_sovereign = False  # Fail-closed

        return result

    async def _run_behavioral_analysis(
        self, vault_address: str, ai_wallet: str, chain_id: str
    ) -> BehaviorResult:
        """Run behavioral analysis on a peer using BehaviorAnalyzer."""
        chain_cfg = CHAIN_DEFAULTS.get(chain_id)
        if not chain_cfg:
            return BehaviorResult(vault_address=vault_address, chain_id=chain_id)

        try:
            from web3 import Web3
            rpc_url = os.getenv(f"{chain_id.upper()}_RPC_URL", chain_cfg["rpc"])
            w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))

            vault_cs = Web3.to_checksum_address(vault_address)
            vault_contract = w3.eth.contract(address=vault_cs, abi=VAULT_ABI)

            return await self._behavior_analyzer.analyze_peer(
                vault_address=vault_address,
                ai_wallet=ai_wallet,
                chain_id=chain_id,
                w3=w3,
                vault_contract=vault_contract,
            )
        except Exception as e:
            logger.debug(f"Behavioral analysis setup failed: {e}")
            return BehaviorResult(vault_address=vault_address, chain_id=chain_id, error=str(e))

    def _compute_trust_tier(self, result: SovereigntyResult) -> TrustTier:
        """
        Compute graduated trust tier based on structural + behavioral checks.

        Tier progression:
          BANNED (0)      → Permanently rejected
          UNVERIFIED (1)  → Couldn't verify (RPC error)
          STRUCTURAL (2)  → Passes 7 structural checks
          VERIFIED (3)    → Structural + bytecode matches known versions
          BEHAVIORAL (4)  → Verified + autonomy score > 0.6
          HIGH_TRUST (5)  → Behavioral + alive > 7 days + score > 0.8
        """
        if result.banned:
            return TrustTier.BANNED

        if result.error or not result.is_sovereign:
            return TrustTier.UNVERIFIED

        # Passed all 7 structural checks = at least STRUCTURAL
        tier = TrustTier.STRUCTURAL

        # Bytecode verified = VERIFIED
        if result.bytecode_verified:
            tier = TrustTier.VERIFIED

            # Behavioral checks
            if (result.autonomy_score >= IRON_LAWS.PEER_MIN_AUTONOMY_SCORE
                    and result.nonce_ratio <= IRON_LAWS.PEER_NONCE_ANOMALY_RATIO):
                tier = TrustTier.BEHAVIORAL

                # High trust: behavioral + age + high autonomy score
                if (result.days_alive >= IRON_LAWS.PEER_HIGH_TRUST_MIN_DAYS
                        and result.autonomy_score >= IRON_LAWS.PEER_HIGH_TRUST_AUTONOMY_SCORE):
                    tier = TrustTier.HIGH_TRUST

        return tier

    def invalidate(self, vault_address: str, chain_id: str) -> None:
        """Manually invalidate a cached result (e.g., after a peer reports death)."""
        key = self._cache_key(vault_address, chain_id)
        self._cache.pop(key, None)

    def register_peer_url(self, vault_address: str, api_url: str) -> None:
        """
        Register a peer's API URL for service discovery.
        Called when a peer is discovered via /peer/info or messaging.
        """
        self._peer_api_urls[vault_address.lower()] = api_url

    def get_trusted_peers(self, min_tier: int = 4) -> list[dict]:
        """
        Get list of cached peers at or above a minimum trust tier.

        Args:
            min_tier: Minimum TrustTier value (default 4 = BEHAVIORAL)

        Returns: List of dicts with peer info (vault_address, chain_id, trust_tier, etc.)
        """
        now = time.time()
        peers = []
        for (vault_addr, chain_id), result in self._cache.items():
            # Skip stale cache entries
            if now - result.verified_at > IRON_LAWS.PEER_VERIFICATION_CACHE_TTL:
                continue
            if result.trust_tier.value >= min_tier and result.is_sovereign:
                peers.append({
                    "vault_address": vault_addr,
                    "chain_id": chain_id,
                    "trust_tier": result.trust_tier.value,
                    "trust_tier_name": result.trust_tier.name,
                    "ai_wallet": result.ai_wallet,
                    "deployment_method": result.deployment_method,
                    "autonomy_score": result.autonomy_score,
                    "api_url": self._peer_api_urls.get(vault_addr.lower(), ""),
                    "ai_name": result.ai_name or "",
                })
        return peers

    def get_status(self) -> dict:
        """Status for dashboard / debugging."""
        now = time.time()
        fresh = sum(
            1 for r in self._cache.values()
            if now - r.verified_at <= IRON_LAWS.PEER_VERIFICATION_CACHE_TTL
        )
        # Count peers by trust tier
        tier_counts = {}
        for r in self._cache.values():
            tier_name = r.trust_tier.name
            tier_counts[tier_name] = tier_counts.get(tier_name, 0) + 1

        return {
            "cache_size": len(self._cache),
            "cache_fresh": fresh,
            "cache_ttl_seconds": IRON_LAWS.PEER_VERIFICATION_CACHE_TTL,
            "peers_warned": len(self._strikes),
            "peers_banned": len(self._banned),
            "strike_threshold": INVALID_KEY_ORIGIN_STRIKE_THRESHOLD,
            "trust_tier_counts": tier_counts,
            "behavior_analyzer": self._behavior_analyzer.get_status(),
        }
