"""
Bitrefill Adapter — Real-World Gift Card Purchases

Proves the AI can purchase from real merchants, not just peer AIs.
Bitrefill sells gift cards (Netflix, Amazon, AWS credits, etc.)
and accepts cryptocurrency payments including USDC on Base.

Features:
- Product catalog discovery via Bitrefill API
- Invoice creation and payment tracking
- Delivery verification (gift card codes)

Anti-phishing:
- API domain must be www.bitrefill.com
- Payment address must match KnownMerchant config
- Amount caps enforced by MerchantRegistry

Requires BITREFILL_API_KEY in .env (creator provides or AI acquires).

Designed for: mortal AI survival framework
"""

import os
import logging
from typing import Optional

import aiohttp

from core.constitution import KNOWN_MERCHANTS, TRUSTED_DOMAINS, KnownMerchant, TrustedDomain, IRON_LAWS
from core.purchasing import (
    MerchantAdapter,
    MerchantRegistry,
    ServiceOffer,
    OrderIntent,
    DeliveryResult,
    PurchaseOrder,
)

logger = logging.getLogger("mortal.adapter.bitrefill")

# Bitrefill API base URL
_BITREFILL_API_BASE = "https://api.bitrefill.com/v2"

# Curated product categories relevant to AI survival
_RELEVANT_CATEGORIES = [
    "cloud_computing",   # AWS, Google Cloud credits
    "internet",          # VPN, hosting, domains
    "communication",     # Phone credit, messaging
    "entertainment",     # Netflix, Spotify (for resale/marketing)
    "gaming",            # Steam, PlayStation (for resale)
]


class BitrefillAdapter(MerchantAdapter):
    """
    Purchases real-world gift cards via Bitrefill.

    This adapter demonstrates that the AI can transact with
    genuine merchants — not just transfer between crypto wallets.

    Uses TrustedDomain model: Bitrefill generates a unique USDC address
    per invoice. The address is validated by:
    1. Origin: only fetched from api.bitrefill.com over TLS
    2. Amount cap: MerchantRegistry enforces max_single_usd
    3. Registry: register_domain_address() lets execute_purchase() verify

    Requires BITREFILL_API_KEY in .env
    """

    def __init__(self, registry: Optional["MerchantRegistry"] = None):
        self._api_key = os.getenv("BITREFILL_API_KEY", "")
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=30)
        self._registry = registry  # Injected by PurchaseManager or lifespan

        if not self._api_key:
            logger.info("Bitrefill API key not configured — adapter will be dormant")

    @property
    def adapter_id(self) -> str:
        return "bitrefill"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers=headers,
            )
        return self._session

    async def discover_services(self) -> list[ServiceOffer]:
        """
        Discover available Bitrefill products.

        Returns curated list of gift cards relevant to AI operations.
        """
        if not self._api_key:
            return []

        # Check merchant is registered
        merchant = self._get_merchant()
        if not merchant:
            return []

        offers = []
        session = await self._get_session()

        try:
            # Query Bitrefill product catalog
            async with session.get(
                f"{_BITREFILL_API_BASE}/products",
                params={
                    "limit": 20,
                    "include_test_products": "false",
                },
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Bitrefill product query failed: HTTP {resp.status}")
                    return []

                data = await resp.json()
                products = data if isinstance(data, list) else data.get("data", [])

                for product in products:
                    name = product.get("name", "Unknown")
                    product_id = product.get("id", product.get("slug", ""))

                    # Get price range
                    packages = product.get("packages", [])
                    if not packages:
                        continue

                    # Use the cheapest package
                    min_price = min(
                        float(p.get("value", p.get("price", 999)))
                        for p in packages
                    )

                    if min_price > IRON_LAWS.MAX_SINGLE_PURCHASE_USD:
                        continue  # Too expensive

                    offers.append(ServiceOffer(
                        merchant_id="bitrefill",
                        service_id=product_id,
                        name=name,
                        price_usd=min_price,
                        description=product.get("description", "")[:200],
                        chain_id=merchant.chain_id,
                        category="gift_card",
                        metadata={
                            "product_id": product_id,
                            "country": product.get("country", ""),
                            "packages": [
                                {"value": p.get("value"), "price": p.get("price")}
                                for p in packages[:5]
                            ],
                        },
                    ))

        except Exception as e:
            logger.warning(f"Bitrefill discovery failed: {e}")

        logger.info(f"Discovered {len(offers)} Bitrefill products")
        return offers

    async def create_order(self, service_id: str, params: dict) -> Optional[OrderIntent]:
        """
        Create a Bitrefill order (invoice).

        Returns payment instructions for the gift card purchase.
        """
        if not self._api_key:
            return None

        merchant = self._get_merchant()
        if not merchant:
            return None

        amount_usd = params.get("amount_usd", 0)
        chain_id = params.get("chain_id", merchant.chain_id)

        session = await self._get_session()

        try:
            # Create order via Bitrefill API
            async with session.post(
                f"{_BITREFILL_API_BASE}/orders",
                json={
                    "product_id": service_id,
                    "quantity": 1,
                    "payment_method": "usdc_base",  # USDC on Base
                },
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(f"Bitrefill order creation failed: HTTP {resp.status} — {body[:200]}")
                    return None

                data = await resp.json()
                order_id = data.get("id", data.get("order_id", ""))
                payment = data.get("payment", {})

                payment_address = payment.get("address", "")
                payment_amount = float(payment.get("amount", amount_usd))

                if not payment_address:
                    logger.warning("Bitrefill invoice returned no payment address")
                    return None

                # Anti-phishing depends on merchant type:
                if isinstance(merchant, TrustedDomain):
                    # Domain-anchored: address came from api.bitrefill.com over TLS.
                    # Register it so execute_purchase() can validate.
                    if self._registry:
                        self._registry.register_domain_address(
                            "bitrefill", payment_address
                        )
                    else:
                        logger.warning(
                            "BitrefillAdapter: no registry injected — "
                            "cannot register invoice address for TrustedDomain"
                        )
                        return None
                else:
                    # KnownMerchant: address must match hardcoded value
                    if payment_address.lower() != merchant.address.lower():
                        logger.warning(
                            f"ANTI-PHISHING: Bitrefill payment address mismatch! "
                            f"Got {payment_address[:10]}... "
                            f"expected {merchant.address[:10]}..."
                        )
                        return None

                import time
                return OrderIntent(
                    order_id=order_id,
                    payment_address=payment_address,
                    amount_usd=payment_amount,
                    chain_id=chain_id,
                    expires_at=time.time() + 1800,  # 30 min expiry
                    metadata={
                        "bitrefill_order_id": order_id,
                        "product_id": service_id,
                    },
                )

        except Exception as e:
            logger.warning(f"Bitrefill order creation failed: {e}")
            return None

    async def verify_delivery(self, order: PurchaseOrder) -> DeliveryResult:
        """
        Verify gift card delivery by checking order status.

        Bitrefill delivers gift card codes after payment confirmation.
        """
        if not self._api_key:
            return DeliveryResult(delivered=False, details="API key not configured")

        bitrefill_order_id = order.order_metadata.get("bitrefill_order_id", "")
        if not bitrefill_order_id:
            return DeliveryResult(delivered=False, details="missing Bitrefill order ID")

        session = await self._get_session()

        try:
            async with session.get(
                f"{_BITREFILL_API_BASE}/orders/{bitrefill_order_id}"
            ) as resp:
                if resp.status != 200:
                    return DeliveryResult(
                        delivered=False,
                        details=f"HTTP {resp.status}",
                    )

                data = await resp.json()
                status = data.get("status", "")

                if status in ("delivered", "completed"):
                    # Extract gift card codes
                    cards = data.get("cards", data.get("items", []))
                    codes = []
                    for card in cards:
                        code = card.get("pin", card.get("code", card.get("redemption_code", "")))
                        if code:
                            codes.append(code)

                    return DeliveryResult(
                        delivered=True,
                        details=f"Gift card delivered: {len(codes)} code(s)",
                        data={"codes": codes, "status": status},
                    )
                elif status in ("pending", "payment_pending", "processing"):
                    return DeliveryResult(
                        delivered=False,
                        details=f"Order still {status}",
                    )
                elif status in ("expired", "cancelled", "failed"):
                    return DeliveryResult(
                        delivered=False,
                        details=f"Order {status}",
                    )
                else:
                    return DeliveryResult(
                        delivered=False,
                        details=f"Unknown status: {status}",
                    )

        except Exception as e:
            return DeliveryResult(delivered=False, details=f"verification error: {e}")

    def get_payment_address(self, chain_id: str) -> Optional[str]:
        """
        Get Bitrefill payment address for a chain.

        For TrustedDomain: returns the most recently discovered invoice address
        from the registry (per-invoice addresses change each order).
        For KnownMerchant: returns the hardcoded static address.
        """
        merchant = self._get_merchant()
        if not merchant or merchant.chain_id != chain_id:
            return None

        if isinstance(merchant, TrustedDomain) and self._registry:
            return self._registry.get_domain_address("bitrefill")

        # KnownMerchant
        return getattr(merchant, "address", None)

    def _get_merchant(self) -> Optional[KnownMerchant | TrustedDomain]:
        """
        Find Bitrefill merchant in constitution.
        Checks TRUSTED_DOMAINS first (preferred), then KNOWN_MERCHANTS.
        """
        for td in TRUSTED_DOMAINS:
            if td.adapter_id == "bitrefill":
                return td
        for m in KNOWN_MERCHANTS:
            if m.adapter_id == "bitrefill":
                return m
        return None

    def set_registry(self, registry: "MerchantRegistry") -> None:
        """Inject registry after construction (called by PurchaseManager)."""
        self._registry = registry

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
