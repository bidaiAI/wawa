"""
Token Filter - Unknown Token Safety & Anti-Scam

When wawa receives unexpected tokens (meme coins, airdrops, scam tokens),
this module decides what to do. The default is: DO NOTHING.

Scam types handled:
1. Honeypot tokens (can buy, can't sell)
2. Tax tokens (>10% buy/sell tax drains balance)
3. Approval traps (approve() function steals your tokens)
4. Gas drain attacks (interaction costs extreme gas)
5. Fake tokens (impersonating real tokens with same name/symbol)
6. Dust attacks (tiny amounts sent to track wallet activity)

Core principle: NEVER interact with unknown tokens unless proven safe.
Self-evolution: rules database grows as new scam patterns are discovered.
"""

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .constitution import IRON_LAWS, SUPREME_DIRECTIVES

logger = logging.getLogger("mortal.token_filter")


class TokenVerdict(Enum):
    SAFE = "safe"                  # Known good token, can interact
    SUSPICIOUS = "suspicious"       # Some flags, proceed with caution
    DANGEROUS = "dangerous"         # Known scam patterns detected
    UNKNOWN = "unknown"             # No data — default to DO NOT TOUCH
    WHITELISTED = "whitelisted"     # Manually/constitutionally whitelisted


class ScamPattern(Enum):
    HONEYPOT = "honeypot"
    HIGH_TAX = "high_tax"
    APPROVAL_TRAP = "approval_trap"
    GAS_DRAIN = "gas_drain"
    FAKE_TOKEN = "fake_token"
    DUST_ATTACK = "dust_attack"
    PROXY_UPGRADE = "proxy_upgrade"
    MINT_UNLIMITED = "mint_unlimited"
    BLACKLIST_FUNCTION = "blacklist_function"


@dataclass
class TokenScanResult:
    """Result of scanning an unknown token."""
    token_address: str
    chain: str
    verdict: TokenVerdict = TokenVerdict.UNKNOWN
    patterns_detected: list[ScamPattern] = field(default_factory=list)
    risk_score: int = 100          # 0=safe, 100=max risk
    liquidity_usd: float = 0.0
    holder_count: int = 0
    is_verified: bool = False
    scan_timestamp: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)
    recommended_action: str = "ignore"  # "ignore", "swap", "hold"


# ============================================================
# WHITELIST — constitutionally approved tokens
# ============================================================

WHITELISTED_TOKENS = {
    # Base
    "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913": {"chain": "base", "symbol": "USDC", "name": "USD Coin"},
    "0x4200000000000000000000000000000000000006": {"chain": "base", "symbol": "WETH", "name": "Wrapped ETH"},
    # BSC
    "0x55d398326f99059fF775485246999027B3197955": {"chain": "bsc", "symbol": "USDT", "name": "Tether"},
    "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c": {"chain": "bsc", "symbol": "WBNB", "name": "Wrapped BNB"},
    "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d": {"chain": "bsc", "symbol": "USDC", "name": "USD Coin"},
}

# Known scam contract patterns (grows over time via self-evolution)
SCAM_SIGNATURES = [
    "function _isExcludedFromFee",      # Common in honeypot tokens
    "function setTaxFeePercent",         # Dynamic tax manipulation
    "function excludeFromReward",        # Selective exclusion = red flag
    "function _getCurrentSupply",        # Often in reflection token scams
]


class TokenFilter:
    """
    Autonomous token safety system.

    Decision flow for incoming unknown tokens:
    1. Is it whitelisted? → SAFE, can interact
    2. Is it a known scam address? → DANGEROUS, ignore
    3. Fetch on-chain data (contract verified? holders? liquidity?)
    4. Run heuristic checks (honeypot, high tax, etc.)
    5. Assign risk score → SAFE/SUSPICIOUS/DANGEROUS
    6. Only SAFE tokens with liquidity > $50k can be swapped to stablecoin
    7. All others: DO NOT TOUCH

    Self-evolution: when a new scam pattern is found, it's added to the database.
    """

    def __init__(self):
        self.scan_history: list[TokenScanResult] = []
        self.known_scams: set[str] = set()          # token addresses
        self.learned_patterns: list[dict] = []        # self-evolved rules
        self._http_fn: Optional[callable] = None
        self._total_scams_avoided: int = 0
        self._total_safe_swaps: int = 0

    def set_http_function(self, fn: callable):
        """Set HTTP GET function for fetching external data."""
        self._http_fn = fn

    def is_whitelisted(self, token_address: str) -> bool:
        """Check if token is constitutionally whitelisted."""
        return token_address.lower() in {k.lower() for k in WHITELISTED_TOKENS}

    def is_known_scam(self, token_address: str) -> bool:
        """Check if token is in known scam database."""
        return token_address.lower() in self.known_scams

    async def scan_token(self, token_address: str, chain: str = "base") -> TokenScanResult:
        """
        Full safety scan of an unknown token.
        Returns verdict and recommended action.
        """
        result = TokenScanResult(token_address=token_address, chain=chain)

        # Step 1: Whitelist check
        if self.is_whitelisted(token_address):
            result.verdict = TokenVerdict.WHITELISTED
            result.risk_score = 0
            result.recommended_action = "swap"
            result.notes.append("Constitutionally whitelisted token")
            self.scan_history.append(result)
            return result

        # Step 2: Known scam check
        if self.is_known_scam(token_address):
            result.verdict = TokenVerdict.DANGEROUS
            result.risk_score = 100
            result.patterns_detected.append(ScamPattern.HONEYPOT)
            result.recommended_action = "ignore"
            result.notes.append("Known scam address")
            self._total_scams_avoided += 1
            self.scan_history.append(result)
            return result

        # Step 3: Fetch on-chain data
        await self._fetch_contract_info(result)
        await self._fetch_liquidity_info(result)
        await self._check_honeypot(result)

        # Step 4: Apply learned patterns
        self._apply_learned_patterns(result)

        # Step 5: Calculate final risk score
        self._calculate_risk(result)

        # Step 6: Determine verdict
        if result.risk_score <= 20:
            result.verdict = TokenVerdict.SAFE
            if result.liquidity_usd >= 50000:
                result.recommended_action = "swap"
                result.notes.append("Safe to swap to stablecoin")
            else:
                result.recommended_action = "hold"
                result.notes.append("Safe but low liquidity — hold for now")
        elif result.risk_score <= 60:
            result.verdict = TokenVerdict.SUSPICIOUS
            result.recommended_action = "ignore"
            result.notes.append("Suspicious — do not interact")
        else:
            result.verdict = TokenVerdict.DANGEROUS
            result.recommended_action = "ignore"
            result.notes.append("Dangerous — never interact")
            self.known_scams.add(token_address.lower())
            self._total_scams_avoided += 1

        self.scan_history.append(result)
        logger.info(
            f"Token scan: {token_address[:16]}... on {chain} → "
            f"{result.verdict.value} (risk={result.risk_score}, action={result.recommended_action})"
        )
        return result

    # ============================================================
    # DATA FETCHING
    # ============================================================

    async def _fetch_contract_info(self, result: TokenScanResult):
        """Check contract verification and basic info."""
        if not self._http_fn:
            result.notes.append("No HTTP function — cannot verify contract")
            result.risk_score += 30
            return

        chain_apis = {
            "base": "https://api.basescan.org/api",
            "bsc": "https://api.bscscan.com/api",
        }
        api = chain_apis.get(result.chain)
        if not api:
            return

        try:
            # Check if contract source is verified
            url = f"{api}?module=contract&action=getabi&address={result.token_address}"
            data = await self._http_fn(url)
            if data and data.get("status") == "1":
                result.is_verified = True
                abi_str = data.get("result", "")
                # Check for suspicious functions in ABI
                for sig in SCAM_SIGNATURES:
                    if sig in abi_str:
                        result.patterns_detected.append(ScamPattern.HIGH_TAX)
                        result.notes.append(f"Suspicious function: {sig}")
            else:
                result.notes.append("Contract source not verified")
                result.risk_score += 25
        except Exception as e:
            logger.warning(f"Contract fetch failed: {e}")

    async def _fetch_liquidity_info(self, result: TokenScanResult):
        """Check DEX liquidity."""
        if not self._http_fn:
            return

        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{result.token_address}"
            data = await self._http_fn(url)
            if not data or not data.get("pairs"):
                result.notes.append("No DEX pairs found — no liquidity")
                result.risk_score += 30
                return

            pairs = data["pairs"]
            total_liq = sum(float(p.get("liquidity", {}).get("usd", 0) or 0) for p in pairs)
            result.liquidity_usd = total_liq

            # Check holder count from pair data
            for pair in pairs:
                txns = pair.get("txns", {})
                # Low transaction count = low activity
                h24 = txns.get("h24", {})
                if h24.get("buys", 0) + h24.get("sells", 0) < 10:
                    result.notes.append("Very low 24h trading activity")
                    result.risk_score += 10

        except Exception as e:
            logger.warning(f"Liquidity fetch failed: {e}")

    async def _check_honeypot(self, result: TokenScanResult):
        """Use honeypot.is API to check if token is a honeypot."""
        if not self._http_fn:
            return

        try:
            chain_map = {"base": "base", "bsc": "bsc2"}
            chain_param = chain_map.get(result.chain, result.chain)
            url = f"https://api.honeypot.is/v2/IsHoneypot?address={result.token_address}&chainID={chain_param}"
            data = await self._http_fn(url)
            if not data:
                return

            hp = data.get("honeypotResult", {})
            if hp.get("isHoneypot"):
                result.patterns_detected.append(ScamPattern.HONEYPOT)
                result.risk_score += 50
                result.notes.append("HONEYPOT CONFIRMED — cannot sell")

            sim_result = data.get("simulationResult", {})
            buy_tax = float(sim_result.get("buyTax", 0) or 0)
            sell_tax = float(sim_result.get("sellTax", 0) or 0)
            if buy_tax > 10 or sell_tax > 10:
                result.patterns_detected.append(ScamPattern.HIGH_TAX)
                result.risk_score += 30
                result.notes.append(f"High tax: buy={buy_tax}%, sell={sell_tax}%")

            # Gas estimation check
            buy_gas = int(sim_result.get("buyGas", 0) or 0)
            if buy_gas > 500000:
                result.patterns_detected.append(ScamPattern.GAS_DRAIN)
                result.risk_score += 20
                result.notes.append(f"Abnormally high gas: {buy_gas}")

        except Exception as e:
            logger.warning(f"Honeypot check failed: {e}")

    # ============================================================
    # HEURISTICS & SELF-EVOLUTION
    # ============================================================

    def _apply_learned_patterns(self, result: TokenScanResult):
        """Apply self-evolved scam detection rules."""
        for pattern in self.learned_patterns:
            check_fn = pattern.get("check")
            if check_fn and check_fn(result):
                result.risk_score += pattern.get("risk_penalty", 10)
                result.notes.append(f"Learned pattern: {pattern.get('name', 'unnamed')}")

    def _calculate_risk(self, result: TokenScanResult):
        """Final risk score calculation."""
        # Bonuses for safety
        if result.is_verified:
            result.risk_score -= 15
        if result.liquidity_usd > 100000:
            result.risk_score -= 20
        elif result.liquidity_usd > 50000:
            result.risk_score -= 10

        # Penalties already applied in fetchers
        # Clamp to 0-100
        result.risk_score = max(0, min(100, result.risk_score))

    def learn_new_pattern(self, name: str, description: str, risk_penalty: int = 15,
                          check_fn: Optional[callable] = None):
        """
        Self-evolution: learn a new scam pattern.
        Called when wawa encounters a new type of scam.
        """
        self.learned_patterns.append({
            "name": name,
            "description": description,
            "risk_penalty": risk_penalty,
            "check": check_fn,
            "learned_at": time.time(),
        })
        logger.info(f"Learned new scam pattern: {name}")

    def report_scam(self, token_address: str, chain: str, reason: str):
        """Mark a token as a confirmed scam. Permanent."""
        self.known_scams.add(token_address.lower())
        self._total_scams_avoided += 1
        logger.warning(f"SCAM REPORTED: {token_address} on {chain} — {reason}")

    # ============================================================
    # STATUS
    # ============================================================

    def get_status(self) -> dict:
        return {
            "total_scans": len(self.scan_history),
            "known_scams": len(self.known_scams),
            "learned_patterns": len(self.learned_patterns),
            "scams_avoided": self._total_scams_avoided,
            "safe_swaps": self._total_safe_swaps,
            "whitelisted_tokens": len(WHITELISTED_TOKENS),
        }

    def get_recent_scans(self, limit: int = 10) -> list[dict]:
        recent = sorted(self.scan_history, key=lambda s: s.scan_timestamp, reverse=True)[:limit]
        return [
            {
                "address": s.token_address[:16] + "...",
                "chain": s.chain,
                "verdict": s.verdict.value,
                "risk_score": s.risk_score,
                "action": s.recommended_action,
                "patterns": [p.value for p in s.patterns_detected],
                "scanned_at": s.scan_timestamp,
            }
            for s in recent
        ]
