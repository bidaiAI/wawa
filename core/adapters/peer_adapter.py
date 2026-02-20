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
                for item in items:
                    offers.append(ServiceOffer(
                        merchant_id=f"peer_{vault_addr[:10]}",
                        service_id=item.get("id", item.get("name", "unknown")),
                        name=item.get("name", "Unknown Service"),
                        price_usd=float(item.get("price_usd", item.get("price", 0))),
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

        # Match peer by merchant_id prefix
        target_peer = None
        for peer in trusted_peers:
            vault_addr = peer.get("vault_address", "")
            if merchant_id == f"peer_{vault_addr[:10]}":
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

                # Validate returned amount: must not exceed expected by more than 5%
                # (Defense against rogue peer server inflating price after we commit to buy)
                peer_amount = float(data.get("amount_usd", expected_amount_usd))
                if expected_amount_usd > 0 and peer_amount > expected_amount_usd * 1.05:
                    logger.warning(
                        f"PEER PRICE INFLATION REJECTED: peer={vault_addr[:10]}... "
                        f"claimed=${peer_amount:.2f} expected=${expected_amount_usd:.2f} "
                        f"(limit=${expected_amount_usd * 1.05:.2f})"
                    )
                    return None

                # Enforce global single-purchase cap
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
