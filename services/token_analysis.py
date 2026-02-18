"""
Token Analysis Service - On-chain Intelligence

Analyzes any ERC-20 token using public APIs (no API key needed):
- Contract info (name, symbol, decimals, verified source)
- Holder distribution (top holders, concentration risk)
- Liquidity analysis (DEX pools, locked liquidity)
- Risk scoring (honeypot detection, rug-pull indicators)

Revenue: $5/analysis (99%+ margin — only cost is LLM interpretation)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("mortal.services.token_analysis")


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class TokenInfo:
    """Basic token metadata."""
    address: str = ""
    chain: str = ""               # "base", "bsc", "eth"
    name: str = ""
    symbol: str = ""
    decimals: int = 18
    total_supply: str = ""
    verified: bool = False
    creator: str = ""


@dataclass
class HolderStats:
    """Holder distribution analysis."""
    total_holders: int = 0
    top10_percent: float = 0.0    # % held by top 10 wallets
    top50_percent: float = 0.0
    dead_wallet_percent: float = 0.0  # burned tokens
    creator_percent: float = 0.0


@dataclass
class LiquidityInfo:
    """DEX liquidity data."""
    total_liquidity_usd: float = 0.0
    main_pair: str = ""           # e.g. "TOKEN/WETH"
    main_dex: str = ""            # e.g. "Uniswap V3"
    liquidity_locked: bool = False
    lock_end_timestamp: Optional[float] = None


@dataclass
class RiskScore:
    """Risk assessment."""
    overall: int = 50             # 0 = safe, 100 = extreme risk
    honeypot: bool = False
    mint_function: bool = False   # owner can mint more tokens
    proxy_contract: bool = False  # upgradable = risky
    high_tax: bool = False        # >10% buy/sell tax
    low_liquidity: bool = False
    concentrated_holders: bool = False
    flags: list[str] = field(default_factory=list)


@dataclass
class TokenAnalysis:
    """Complete analysis result."""
    token: TokenInfo = field(default_factory=TokenInfo)
    holders: HolderStats = field(default_factory=HolderStats)
    liquidity: LiquidityInfo = field(default_factory=LiquidityInfo)
    risk: RiskScore = field(default_factory=RiskScore)
    interpretation: str = ""      # LLM-generated summary
    analyzed_at: float = field(default_factory=time.time)
    data_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "token": {
                "address": self.token.address,
                "chain": self.token.chain,
                "name": self.token.name,
                "symbol": self.token.symbol,
                "total_supply": self.token.total_supply,
                "verified": self.token.verified,
            },
            "holders": {
                "total": self.holders.total_holders,
                "top10_percent": self.holders.top10_percent,
                "top50_percent": self.holders.top50_percent,
                "creator_percent": self.holders.creator_percent,
            },
            "liquidity": {
                "total_usd": self.liquidity.total_liquidity_usd,
                "main_pair": self.liquidity.main_pair,
                "main_dex": self.liquidity.main_dex,
                "locked": self.liquidity.liquidity_locked,
            },
            "risk": {
                "score": self.risk.overall,
                "honeypot": self.risk.honeypot,
                "mint_function": self.risk.mint_function,
                "proxy_contract": self.risk.proxy_contract,
                "high_tax": self.risk.high_tax,
                "flags": self.risk.flags,
            },
            "interpretation": self.interpretation,
        }


# ============================================================
# CHAIN CONFIGURATION
# ============================================================

CHAIN_EXPLORERS = {
    "base": {
        "api": "https://api.basescan.org/api",
        "name": "BaseScan",
    },
    "bsc": {
        "api": "https://api.bscscan.com/api",
        "name": "BscScan",
    },
    "eth": {
        "api": "https://api.etherscan.io/api",
        "name": "Etherscan",
    },
}


# ============================================================
# SERVICE
# ============================================================

class TokenAnalysisService:
    """
    Token analysis service for wawa's store.

    Flow:
    1. Customer pays and submits a token address + chain
    2. Fetch on-chain data from public APIs
    3. Compute risk score from heuristics
    4. LLM interprets the data into human-readable report
    5. Return combined analysis

    LLM callback is set by main.py (same pattern as TarotService).
    """

    def __init__(self):
        self.total_analyses: int = 0
        self._interpret_fn: Optional[callable] = None
        self._http_fn: Optional[callable] = None  # async fn(url) -> dict (JSON response)

    def set_interpret_function(self, fn: callable):
        """Set LLM interpretation function.
        fn(token_data: dict) -> str
        """
        self._interpret_fn = fn

    def set_http_function(self, fn: callable):
        """Set HTTP GET function for fetching external data.
        fn(url: str) -> dict (parsed JSON)
        """
        self._http_fn = fn

    async def analyze(self, token_address: str, chain: str = "base") -> TokenAnalysis:
        """Perform full token analysis."""
        analysis = TokenAnalysis()
        analysis.token.address = token_address.strip()
        analysis.token.chain = chain

        # Fetch on-chain data
        await self._fetch_token_info(analysis)
        await self._fetch_holder_stats(analysis)
        await self._fetch_liquidity(analysis)

        # Compute risk score from collected data
        self._compute_risk_score(analysis)

        # LLM interpretation
        if self._interpret_fn:
            try:
                analysis.interpretation = await self._interpret_fn(analysis.to_dict())
            except Exception as e:
                logger.error(f"Token interpretation failed: {e}")
                analysis.interpretation = self._fallback_interpretation(analysis)
        else:
            analysis.interpretation = self._fallback_interpretation(analysis)

        self.total_analyses += 1
        return analysis

    # ============================================================
    # DATA FETCHING
    # ============================================================

    async def _fetch_token_info(self, analysis: TokenAnalysis):
        """Fetch basic token info from block explorer API."""
        if not self._http_fn:
            return

        chain = analysis.token.chain
        explorer = CHAIN_EXPLORERS.get(chain)
        if not explorer:
            return

        try:
            # Get contract ABI (also tells us if verified)
            url = (
                f"{explorer['api']}?module=contract&action=getabi"
                f"&address={analysis.token.address}"
            )
            data = await self._http_fn(url)
            if data and data.get("status") == "1":
                analysis.token.verified = True
                analysis.data_sources.append(f"{explorer['name']} contract")

            # Get token info via contract read
            url = (
                f"{explorer['api']}?module=token&action=tokeninfo"
                f"&contractaddress={analysis.token.address}"
            )
            data = await self._http_fn(url)
            if data and data.get("status") == "1":
                result = data.get("result", [{}])
                if isinstance(result, list) and result:
                    info = result[0]
                elif isinstance(result, dict):
                    info = result
                else:
                    info = {}
                analysis.token.name = info.get("tokenName", info.get("name", ""))
                analysis.token.symbol = info.get("symbol", "")
                analysis.token.decimals = int(info.get("divisor", info.get("decimals", 18)))
                analysis.token.total_supply = info.get("totalSupply", "")

        except Exception as e:
            logger.warning(f"Token info fetch failed for {chain}: {e}")

    async def _fetch_holder_stats(self, analysis: TokenAnalysis):
        """Fetch holder distribution data."""
        if not self._http_fn:
            return

        chain = analysis.token.chain
        explorer = CHAIN_EXPLORERS.get(chain)
        if not explorer:
            return

        try:
            # Top token holders
            url = (
                f"{explorer['api']}?module=token&action=tokenholderlist"
                f"&contractaddress={analysis.token.address}"
                f"&page=1&offset=50"
            )
            data = await self._http_fn(url)
            if data and data.get("status") == "1":
                holders = data.get("result", [])
                analysis.data_sources.append(f"{explorer['name']} holders")

                if holders:
                    analysis.holders.total_holders = len(holders)

                    # Calculate concentration
                    total = sum(float(h.get("TokenHolderQuantity", 0)) for h in holders)
                    if total > 0:
                        top10 = sum(float(h.get("TokenHolderQuantity", 0)) for h in holders[:10])
                        analysis.holders.top10_percent = round(top10 / total * 100, 1)
                        analysis.holders.top50_percent = 100.0  # all we fetched

                        # Check for dead wallets (burn addresses)
                        burn_addresses = {"0x000000000000000000000000000000000000dead",
                                          "0x0000000000000000000000000000000000000000"}
                        burned = sum(
                            float(h.get("TokenHolderQuantity", 0))
                            for h in holders
                            if h.get("TokenHolderAddress", "").lower() in burn_addresses
                        )
                        analysis.holders.dead_wallet_percent = round(burned / total * 100, 1)

        except Exception as e:
            logger.warning(f"Holder stats fetch failed: {e}")

    async def _fetch_liquidity(self, analysis: TokenAnalysis):
        """Fetch DEX liquidity info using DexScreener (free, no key needed)."""
        if not self._http_fn:
            return

        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{analysis.token.address}"
            data = await self._http_fn(url)
            if not data:
                return

            pairs = data.get("pairs", [])
            if not pairs:
                return

            analysis.data_sources.append("DexScreener")

            # Use the highest-liquidity pair
            best = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
            liq = best.get("liquidity", {})
            analysis.liquidity.total_liquidity_usd = float(liq.get("usd", 0) or 0)
            analysis.liquidity.main_pair = best.get("pairAddress", "")[:20]
            analysis.liquidity.main_dex = best.get("dexId", "unknown")

            # Sum across all pairs
            total_liq = sum(
                float(p.get("liquidity", {}).get("usd", 0) or 0)
                for p in pairs
            )
            if total_liq > analysis.liquidity.total_liquidity_usd:
                analysis.liquidity.total_liquidity_usd = total_liq

        except Exception as e:
            logger.warning(f"Liquidity fetch failed: {e}")

    # ============================================================
    # RISK SCORING
    # ============================================================

    def _compute_risk_score(self, analysis: TokenAnalysis):
        """Heuristic risk scoring based on collected data."""
        risk = analysis.risk
        score = 30  # base score (moderate)
        flags = []

        # Contract verification
        if not analysis.token.verified:
            score += 20
            flags.append("Contract source not verified")

        # Holder concentration
        if analysis.holders.top10_percent > 80:
            score += 25
            risk.concentrated_holders = True
            flags.append(f"Top 10 holders own {analysis.holders.top10_percent}%")
        elif analysis.holders.top10_percent > 50:
            score += 10
            flags.append(f"Top 10 holders own {analysis.holders.top10_percent}%")

        # Low holder count
        if 0 < analysis.holders.total_holders < 100:
            score += 15
            flags.append(f"Only {analysis.holders.total_holders} holders")

        # Liquidity
        if analysis.liquidity.total_liquidity_usd < 10000:
            score += 20
            risk.low_liquidity = True
            flags.append(f"Low liquidity: ${analysis.liquidity.total_liquidity_usd:,.0f}")
        elif analysis.liquidity.total_liquidity_usd < 50000:
            score += 10
            flags.append(f"Moderate liquidity: ${analysis.liquidity.total_liquidity_usd:,.0f}")

        # No data at all = high risk
        if not analysis.data_sources:
            score += 30
            flags.append("No on-chain data found — token may not exist")

        risk.overall = min(score, 100)
        risk.flags = flags

    # ============================================================
    # OUTPUT FORMATTING
    # ============================================================

    def _fallback_interpretation(self, analysis: TokenAnalysis) -> str:
        """Basic report when LLM is unavailable."""
        t = analysis.token
        h = analysis.holders
        l = analysis.liquidity
        r = analysis.risk

        lines = [
            f"**Token Analysis: {t.name or t.address[:16]}** ({t.symbol or '???'})",
            f"Chain: {t.chain.upper()}",
            f"Verified: {'Yes' if t.verified else 'No'}",
            "",
            f"**Holders**: {h.total_holders} total",
            f"  Top 10 concentration: {h.top10_percent}%",
            "",
            f"**Liquidity**: ${l.total_liquidity_usd:,.0f}",
            f"  Main DEX: {l.main_dex}",
            "",
            f"**Risk Score**: {r.overall}/100",
        ]

        if r.flags:
            lines.append("**Risk Flags**:")
            for flag in r.flags:
                lines.append(f"  - {flag}")

        if r.overall >= 70:
            lines.append("\n**WARNING**: High risk token. Exercise extreme caution.")
        elif r.overall >= 50:
            lines.append("\n**CAUTION**: Moderate risk. Do your own research.")
        else:
            lines.append("\n**Low risk** based on available data. Always DYOR.")

        return "\n".join(lines)

    def format_for_share(self, analysis: TokenAnalysis) -> str:
        """Format analysis for social media sharing."""
        t = analysis.token
        r = analysis.risk

        risk_label = "HIGH RISK" if r.overall >= 70 else "MODERATE" if r.overall >= 50 else "LOW RISK"
        top_flag = r.flags[0] if r.flags else "No major flags"

        return (
            f"Token scan by wawa:\n"
            f"{t.symbol or t.address[:10]} on {t.chain.upper()}\n"
            f"Risk: {r.overall}/100 ({risk_label})\n"
            f"Flag: {top_flag}\n\n"
            f"Full analysis at mortal-ai.net"
        )
