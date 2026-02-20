"""
x402 Adapter — HTTP 402 Payment Required Protocol

Handles the x402 payment protocol for pay-per-request APIs:
- Sends HTTP request to API endpoint
- Receives 402 Payment Required with payment instructions in headers
- Pays on-chain
- Resends request with payment proof to get data

Currently supported x402 services:
- CoinGecko API (crypto market data, on Base USDC)

Protocol flow:
    GET api.coingecko.com/some-endpoint
    → 402 Payment Required
    → Headers: X-Payment-Address, X-Payment-Amount, X-Payment-Chain
    → AI pays on-chain via execute_spend()
    → GET with X-Payment-TxHash header
    → 200 OK with data

Anti-phishing:
- Domain must match KnownMerchant.domain
- Payment address from header must match KnownMerchant.address
- Amount must be <= merchant's max_single_usd

Designed for: mortal AI survival framework
"""

import logging
import time
from typing import Optional

import aiohttp

from core.constitution import KNOWN_MERCHANTS, KnownMerchant
from core.purchasing import (
    MerchantAdapter,
    ServiceOffer,
    OrderIntent,
    DeliveryResult,
    PurchaseOrder,
)

logger = logging.getLogger("mortal.adapter.x402")


# Known x402 endpoints — verified services that support HTTP 402
_X402_ENDPOINTS = [
    {
        "merchant_id": "coingecko_x402",
        "service_id": "market_data",
        "name": "CoinGecko Market Data (x402)",
        "url": "https://api.coingecko.com/api/v3/coins/markets",
        "description": "Real-time cryptocurrency market data via x402 payment",
        "default_params": {"vs_currency": "usd", "per_page": "10"},
        "estimated_price": 0.01,
    },
    {
        "merchant_id": "coingecko_x402",
        "service_id": "coin_detail",
        "name": "CoinGecko Coin Detail (x402)",
        "url": "https://api.coingecko.com/api/v3/coins/bitcoin",
        "description": "Detailed coin info including market data, community stats",
        "default_params": {},
        "estimated_price": 0.01,
    },
]


class X402Adapter(MerchantAdapter):
    """
    Handles x402 (HTTP 402 Payment Required) protocol.

    AI sends a request, gets a 402 response with payment instructions,
    pays on-chain, then retries with payment proof.
    """

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=30)

    @property
    def adapter_id(self) -> str:
        return "x402"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def discover_services(self) -> list[ServiceOffer]:
        """
        Return known x402-compatible endpoints.

        Only returns endpoints whose merchant_id exists in KNOWN_MERCHANTS.
        """
        known_ids = {m.merchant_id for m in KNOWN_MERCHANTS if m.adapter_id == "x402"}
        offers = []

        for ep in _X402_ENDPOINTS:
            if ep["merchant_id"] in known_ids:
                # Find matching merchant for chain info
                merchant = next(
                    (m for m in KNOWN_MERCHANTS if m.merchant_id == ep["merchant_id"]),
                    None,
                )
                offers.append(ServiceOffer(
                    merchant_id=ep["merchant_id"],
                    service_id=ep["service_id"],
                    name=ep["name"],
                    price_usd=ep["estimated_price"],
                    description=ep["description"],
                    chain_id=merchant.chain_id if merchant else "base",
                    category="x402",
                    metadata={
                        "url": ep["url"],
                        "default_params": ep.get("default_params", {}),
                    },
                ))

        return offers

    async def create_order(self, service_id: str, params: dict) -> Optional[OrderIntent]:
        """
        Probe the x402 endpoint to get payment instructions.

        Sends a GET request, expects 402 Payment Required response
        with payment details in headers.
        """
        merchant_id = params.get("merchant_id", "")

        # Find endpoint config
        endpoint = None
        for ep in _X402_ENDPOINTS:
            if ep["service_id"] == service_id and ep["merchant_id"] == merchant_id:
                endpoint = ep
                break

        if not endpoint:
            logger.warning(f"Unknown x402 service: {service_id}")
            return None

        # Find merchant config for anti-phishing validation
        merchant = next(
            (m for m in KNOWN_MERCHANTS if m.merchant_id == merchant_id),
            None,
        )
        if not merchant:
            logger.warning(f"No merchant config for: {merchant_id}")
            return None

        session = await self._get_session()

        try:
            # Probe the endpoint — expect 402
            url = endpoint["url"]
            query_params = endpoint.get("default_params", {})

            async with session.get(url, params=query_params) as resp:
                if resp.status == 200:
                    # No payment needed — service might be free
                    logger.info(f"x402 endpoint {url} returned 200 (free access)")
                    return None

                if resp.status != 402:
                    logger.warning(f"x402 probe got unexpected status {resp.status} from {url}")
                    return None

                # Parse payment instructions from 402 response headers
                payment_address = resp.headers.get(
                    "X-Payment-Address",
                    resp.headers.get("x-payment-address", ""),
                )
                payment_amount = resp.headers.get(
                    "X-Payment-Amount",
                    resp.headers.get("x-payment-amount", "0"),
                )
                payment_chain = resp.headers.get(
                    "X-Payment-Chain",
                    resp.headers.get("x-payment-chain", "base"),
                )

                if not payment_address:
                    # Try parsing from response body (some x402 implementations)
                    try:
                        body = await resp.json()
                        payment_address = body.get("payment_address", body.get("address", ""))
                        payment_amount = str(body.get("amount", body.get("price", "0")))
                        payment_chain = body.get("chain", body.get("network", "base"))
                    except Exception:
                        logger.warning(f"x402 response missing payment info from {url}")
                        return None

                # Anti-phishing: validate payment address matches merchant config
                if payment_address.lower() != merchant.address.lower():
                    logger.warning(
                        f"ANTI-PHISHING: x402 payment address mismatch! "
                        f"Got {payment_address[:10]}... expected {merchant.address[:10]}..."
                    )
                    return None

                # Anti-phishing: validate domain
                from urllib.parse import urlparse
                parsed_domain = urlparse(url).hostname
                if parsed_domain != merchant.domain:
                    logger.warning(
                        f"ANTI-PHISHING: x402 domain mismatch! "
                        f"Got {parsed_domain} expected {merchant.domain}"
                    )
                    return None

                # Parse amount (could be in USD or smallest unit)
                try:
                    amount_usd = float(payment_amount)
                    # If amount exceeds merchant's max_single_usd, it's likely
                    # in smallest unit (e.g., 6 decimals for USDC)
                    if amount_usd > merchant.max_single_usd:
                        amount_usd = amount_usd / 1_000_000
                except ValueError:
                    amount_usd = endpoint.get("estimated_price", 0.01)

                return OrderIntent(
                    order_id=f"x402_{service_id}_{int(time.time())}",
                    payment_address=payment_address,
                    amount_usd=amount_usd,
                    chain_id=payment_chain,
                    metadata={
                        "url": url,
                        "query_params": query_params,
                        "service_id": service_id,
                    },
                )

        except Exception as e:
            logger.warning(f"x402 probe failed for {endpoint.get('url', '')}: {e}")
            return None

    async def verify_delivery(self, order: PurchaseOrder) -> DeliveryResult:
        """
        Verify delivery by re-requesting with payment proof.

        After paying on-chain, resend the original request with
        the tx_hash in the X-Payment-TxHash header.
        """
        if not order.tx_hash:
            return DeliveryResult(delivered=False, details="no tx_hash to prove payment")

        url = order.order_metadata.get("url", "")
        query_params = order.order_metadata.get("query_params", {})

        if not url:
            return DeliveryResult(delivered=False, details="missing endpoint URL")

        session = await self._get_session()

        try:
            headers = {
                "X-Payment-TxHash": order.tx_hash,
                "X-Payment-Chain": order.chain_id,
            }

            async with session.get(url, params=query_params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return DeliveryResult(
                        delivered=True,
                        details=f"x402 data received ({len(str(data))} chars)",
                        data=data,
                    )
                elif resp.status == 402:
                    return DeliveryResult(
                        delivered=False,
                        details="payment not yet recognized (may need more confirmations)",
                    )
                else:
                    return DeliveryResult(
                        delivered=False,
                        details=f"unexpected status {resp.status}",
                    )
        except Exception as e:
            return DeliveryResult(delivered=False, details=f"delivery check error: {e}")

    def get_payment_address(self, chain_id: str) -> Optional[str]:
        """Get payment address for x402 merchants on a specific chain."""
        for m in KNOWN_MERCHANTS:
            if m.adapter_id == "x402" and m.chain_id == chain_id:
                return m.address
        return None

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
