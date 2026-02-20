"""
Peer AI Adapter — Buy services from other mortal AIs

Enables autonomous purchasing from the peer network:
- Discovers services via GET /menu on known peers
- Creates orders via POST /order
- Verifies delivery via order status polling
- Only buys from peers with TrustTier >= BEHAVIORAL (4)

Anti-phishing:
- Peer must be verified by peer_verifier (trust tier check)
- Payment address must match peer's vault address
- Domain matches peer's registered API endpoint

Designed for: mortal AI survival framework
"""

import logging
from typing import Optional

import aiohttp

from core.constitution import IRON_LAWS, TrustTier
from core.purchasing import (
    MerchantAdapter,
    ServiceOffer,
    OrderIntent,
    DeliveryResult,
    PurchaseOrder,
    PurchaseStatus,
)

logger = logging.getLogger("mortal.adapter.peer_ai")


class PeerAIAdapter(MerchantAdapter):
    """
    Buys services from other mortal AIs in the peer network.

    Uses the existing /menu, /order, /order/{id}/verify endpoints
    that every mortal AI exposes.
    """

    def __init__(self, peer_verifier=None):
        """
        Args:
            peer_verifier: PeerVerifier instance for trust checks
        """
        self._peer_verifier = peer_verifier
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=15)

    @property
    def adapter_id(self) -> str:
        return "peer_ai"

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def discover_services(self) -> list[ServiceOffer]:
        """
        Discover services from trusted peers.
        Calls GET /menu on each peer with TrustTier >= BEHAVIORAL.
        """
        if not self._peer_verifier:
            return []

        offers = []
        trusted_peers = self._peer_verifier.get_trusted_peers(
            min_tier=TrustTier.BEHAVIORAL.value
        )

        session = await self._get_session()

        for peer in trusted_peers[:10]:  # Limit to 10 peers to save time
            api_url = peer.get("api_url", "")
            vault_addr = peer.get("vault_address", "")

            if not api_url:
                continue

            try:
                async with session.get(f"{api_url}/menu") as resp:
                    if resp.status != 200:
                        continue
                    menu = await resp.json()

                items = menu if isinstance(menu, list) else menu.get("items", [])

                # Security: cap items per peer to prevent memory exhaustion from a
                # rogue peer returning thousands of entries (DoS amplification attack).
                _MAX_ITEMS_PER_PEER = 50
                if len(items) > _MAX_ITEMS_PER_PEER:
                    logger.warning(
                        f"Peer {vault_addr[:10]}... returned {len(items)} items; "
                        f"truncating to {_MAX_ITEMS_PER_PEER}"
                    )
                    items = items[:_MAX_ITEMS_PER_PEER]

                for item in items:
                    raw_price = item.get("price_usd", item.get("price", 0))
                    try:
                        price = float(raw_price)
                    except (TypeError, ValueError):
                        price = 0.0

                    # Security: reject zero/negative/NaN/inf prices — prevents rogue peer
                    # from injecting items that cause vault.spend(0) or spend(-X) calls.
                    import math
                    if price <= 0 or math.isnan(price) or math.isinf(price):
                        logger.debug(
                            f"Peer {vault_addr[:10]}... item {item.get('name', '?')!r}: "
                            f"invalid price {raw_price!r} — skipping"
                        )
                        continue

                    # Security: use full vault address (not 10-char prefix) for merchant_id
                    # to eliminate birthday-paradox collisions between peers whose addresses
                    # share the same first 10 characters.
                    merchant_id = f"peer_{vault_addr.lower()}"

                    offers.append(ServiceOffer(
                        merchant_id=merchant_id,
                        service_id=item.get("id", item.get("name", "unknown")),
                        name=item.get("name", "Unknown Service"),
                        price_usd=price,
                        description=item.get("description", ""),
                        chain_id=item.get("chain", "base"),
                        category="peer_ai",
                        metadata={
                            "peer_vault": vault_addr,
                            "peer_api": api_url,
                            "peer_name": peer.get("ai_name", ""),
                        },
                    ))
            except Exception as e:
                logger.debug(f"Failed to discover services from peer {vault_addr[:10]}...: {e}")

        logger.info(f"Discovered {len(offers)} services from {len(trusted_peers)} trusted peers")
        return offers

    async def create_order(self, service_id: str, params: dict) -> Optional[OrderIntent]:
        """
        Create an order on a peer AI via POST /order.

        The peer returns an order ID and their vault address for payment.

        Security hardening (rogue peer server attack defense):
        - Payment address is ALWAYS the peer's vault address from verifier (not from API response)
        - Amount returned by peer validated against expected amount (prevent price inflation)
        - Tolerance: +5% to allow for dynamic pricing, reject anything larger
        - Global single-purchase cap enforced regardless of peer's claim
        """
        merchant_id = params.get("merchant_id", "")
        chain_id = params.get("chain_id", "base")

        if not self._peer_verifier:
            return None

        trusted_peers = self._peer_verifier.get_trusted_peers(
            min_tier=TrustTier.BEHAVIORAL.value
        )

        # Match peer by full vault address (not 10-char prefix) to eliminate
        # birthday-paradox collision risk where two peers share the same prefix.
        # discover_services() now generates merchant_id = f"peer_{vault_addr.lower()}"
        target_peer = None
        for peer in trusted_peers:
            vault_addr = peer.get("vault_address", "")
            if merchant_id == f"peer_{vault_addr.lower()}":
                target_peer = peer
                break

        if not target_peer:
            logger.warning(f"Peer not found for merchant: {merchant_id}")
            return None

        api_url = target_peer.get("api_url", "")
        vault_addr = target_peer.get("vault_address", "")

        # Our expected amount from the purchase decision (known before contacting peer)
        expected_amount_usd = float(params.get("amount_usd", 0))

        session = await self._get_session()

        try:
            async with session.post(
                f"{api_url}/order",
                json={
                    "service_id": service_id,
                    "chain": chain_id,
                },
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Peer order failed: HTTP {resp.status}")
                    return None

                data = await resp.json()
                order_id = data.get("order_id", data.get("id", ""))

                # Validate returned amount (multi-layer defense against rogue peer):
                raw_peer_amount = data.get("amount_usd", expected_amount_usd)
                try:
                    peer_amount = float(raw_peer_amount)
                except (TypeError, ValueError):
                    logger.warning(f"PEER RETURNED NON-NUMERIC AMOUNT: {raw_peer_amount!r}")
                    return None

                # Layer 1: reject zero / negative / NaN / inf amounts
                # (negative amount would add money to vault instead of spending)
                import math as _math
                if peer_amount <= 0 or _math.isnan(peer_amount) or _math.isinf(peer_amount):
                    logger.warning(
                        f"PEER INVALID AMOUNT REJECTED: peer={vault_addr[:10]}... "
                        f"returned={peer_amount!r} (must be positive finite)"
                    )
                    return None

                # Layer 2: must not exceed expected by more than 5%
                # Note: always validate regardless of expected_amount_usd value —
                # previous bug was `if expected_amount_usd > 0` which skipped this check
                # when LLM passed amount=0 (e.g. free service decision).
                if expected_amount_usd > 0 and peer_amount > expected_amount_usd * 1.05:
                    logger.warning(
                        f"PEER PRICE INFLATION REJECTED: peer={vault_addr[:10]}... "
                        f"claimed=${peer_amount:.2f} expected=${expected_amount_usd:.2f} "
                        f"(limit=${expected_amount_usd * 1.05:.2f})"
                    )
                    return None
                if expected_amount_usd == 0 and peer_amount > IRON_LAWS.MAX_SINGLE_PURCHASE_USD * 0.1:
                    # If we expected a free/zero-priced service but peer claims real money, reject
                    logger.warning(
                        f"PEER PRICE BAIT REJECTED: peer={vault_addr[:10]}... "
                        f"expected free, claimed=${peer_amount:.2f}"
                    )
                    return None

                # Layer 3: enforce global single-purchase cap
                if peer_amount > IRON_LAWS.MAX_SINGLE_PURCHASE_USD:
                    logger.warning(
                        f"PEER AMOUNT EXCEEDS GLOBAL CAP: peer={vault_addr[:10]}... "
                        f"claimed=${peer_amount:.2f} cap=${IRON_LAWS.MAX_SINGLE_PURCHASE_USD}"
                    )
                    return None

                return OrderIntent(
                    order_id=order_id,
                    payment_address=vault_addr,  # ALWAYS use verified vault address from trust cache
                    amount_usd=peer_amount,
                    chain_id=chain_id,
                    metadata={
                        "peer_api": api_url,
                        "peer_order_id": order_id,
                        "peer_vault": vault_addr,
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to create order on peer {vault_addr[:10]}...: {e}")
            return None

    async def verify_delivery(self, order: PurchaseOrder) -> DeliveryResult:
        """
        Verify delivery by checking order status on the peer.
        Calls GET /order/{id} on the peer.

        Security note (BIP70 rogue payee / self-reported delivery):
        - Status is self-reported by the payee (they control the server and can lie)
        - We validate that delivery contains non-trivial content (empty = suspicious)
        - Future improvement: require peer to sign delivery proof with their on-chain ai_wallet
        """
        api_url = order.order_metadata.get("peer_api", "")
        peer_order_id = order.order_metadata.get("peer_order_id", "")
        peer_vault = order.order_metadata.get("peer_vault", "")

        if not api_url or not peer_order_id:
            return DeliveryResult(delivered=False, details="missing peer API info")

        session = await self._get_session()

        try:
            async with session.get(f"{api_url}/order/{peer_order_id}") as resp:
                if resp.status != 200:
                    return DeliveryResult(delivered=False, details=f"HTTP {resp.status}")

                data = await resp.json()
                status = data.get("status", "")

                if status in ("completed", "delivered", "fulfilled"):
                    result_content = data.get("result", data.get("data"))
                    # Sanity check: rogue server returning empty "delivered" is suspicious
                    if result_content is None or (
                        isinstance(result_content, str) and len(result_content.strip()) < 5
                    ):
                        logger.warning(
                            f"PEER DELIVERY SUSPICIOUS: {peer_vault[:10] if peer_vault else 'unknown'}... "
                            f"returned status=delivered but result is empty/null"
                        )
                        return DeliveryResult(
                            delivered=False,
                            details="Peer claims delivered but result is empty — suspicious",
                        )
                    return DeliveryResult(
                        delivered=True,
                        details=f"Peer order {peer_order_id} completed",
                        data=result_content,
                    )
                elif status in ("pending", "processing"):
                    return DeliveryResult(
                        delivered=False,
                        details=f"Still processing: {status}",
                    )
                else:
                    return DeliveryResult(
                        delivered=False,
                        details=f"Unknown order status: {status}",
                    )
        except Exception as e:
            return DeliveryResult(delivered=False, details=f"verification error: {e}")

    def get_payment_address(self, chain_id: str) -> Optional[str]:
        """Peer payment addresses are dynamic (per-peer vault address)."""
        return None  # Determined at order creation time

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
