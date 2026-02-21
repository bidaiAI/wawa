"""
Purchasing Engine — AI Autonomous Spending

Enables the AI to autonomously purchase services from:
1. Other mortal AIs in the peer network (PeerAIAdapter)
2. x402-compatible APIs like CoinGecko (X402Adapter)
3. Real-world merchants like Bitrefill (BitrefillAdapter)

Architecture:
- MerchantAdapter (ABC): pluggable per-merchant integration
- MerchantRegistry: manages known merchants with anti-phishing checks
- PurchaseManager: orchestrates the full purchase lifecycle

6-layer anti-phishing defense:
1. Constitution hardcoded addresses (KNOWN_MERCHANTS)
2. On-chain whitelist + 5-minute activation delay
3. Domain verification (API domain must match merchant config)
4. Per-merchant + global amount caps
5. LLM evaluation (AI judges if purchase is reasonable)
6. Delivery verification (confirm goods/services received)

Designed for: mortal AI survival framework
"""

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any

from core.constitution import (
    IRON_LAWS,
    KNOWN_MERCHANTS,
    TRUSTED_DOMAINS,
    KnownMerchant,
    TrustedDomain,
)

logger = logging.getLogger("mortal.purchasing")


# ============================================================
# DATA TYPES
# ============================================================

class PurchaseStatus(Enum):
    """Lifecycle states of a purchase order."""
    PENDING_WHITELIST = "pending_whitelist"       # Waiting for address to be whitelisted
    PENDING_ACTIVATION = "pending_activation"     # Whitelisted but activation delay not passed
    PENDING_PAYMENT = "pending_payment"           # Ready to pay on-chain
    PAID = "paid"                                 # On-chain payment sent
    DELIVERED = "delivered"                       # Goods/services received and verified
    FAILED = "failed"                             # Purchase failed at any stage
    CANCELLED = "cancelled"                       # Cancelled by AI decision


@dataclass
class ServiceOffer:
    """A service available for purchase from a merchant."""
    merchant_id: str
    service_id: str
    name: str
    price_usd: float
    description: str
    chain_id: str
    category: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class OrderIntent:
    """Created by adapter after create_order() — contains payment instructions."""
    order_id: str              # Merchant-assigned order ID
    payment_address: str       # Where to send payment
    amount_usd: float          # Exact amount to pay
    chain_id: str              # Which chain to pay on
    expires_at: float = 0.0    # Expiration timestamp (0 = no expiry)
    metadata: dict = field(default_factory=dict)


@dataclass
class DeliveryResult:
    """Result of verifying delivery of purchased goods/services."""
    delivered: bool
    details: str = ""
    data: Any = None           # Delivered content (API response, gift card code, etc.)


@dataclass
class PurchaseOrder:
    """Full lifecycle record of a purchase."""
    id: str
    merchant_id: str
    merchant_name: str
    service_id: str
    service_name: str
    amount_usd: float
    payment_address: str
    chain_id: str
    status: PurchaseStatus
    created_at: float
    reasoning: str = ""        # AI's reason for purchasing
    tx_hash: str = ""
    error: str = ""
    delivered_at: float = 0.0
    delivery_details: str = ""
    delivery_data: dict = field(default_factory=dict)  # Delivered content (e.g. gift card codes). NEVER exposed in to_dict().
    order_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """
        Serialize for public API response.

        IMPORTANT: delivery_data is intentionally excluded here.
        It may contain sensitive content (gift card PINs, redemption codes).
        The AI uses it internally; it is never returned to API callers.
        """
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "merchant_name": self.merchant_name,
            "service_id": self.service_id,
            "service_name": self.service_name,
            "amount_usd": round(self.amount_usd, 2),
            "payment_address": self.payment_address[:10] + "..." if len(self.payment_address) > 10 else self.payment_address,
            "chain_id": self.chain_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "reasoning": self.reasoning,
            "tx_hash": self.tx_hash,
            "error": self.error,
            "delivered_at": self.delivered_at,
            "delivery_details": self.delivery_details,
            # delivery_data deliberately omitted — contains PINs / redemption codes
        }


@dataclass
class PurchaseDecision:
    """AI's decision to purchase something."""
    merchant_id: str
    service_id: str
    amount_usd: float
    reasoning: str
    priority: int = 2          # 1=critical, 2=useful, 3=nice-to-have


# ============================================================
# MERCHANT ADAPTER — Abstract base for all merchant integrations
# ============================================================

class MerchantAdapter(ABC):
    """
    Abstract base class for merchant integrations.

    Each adapter handles one type of merchant interaction
    (peer AIs, x402 APIs, traditional merchants like Bitrefill).
    """

    @property
    @abstractmethod
    def adapter_id(self) -> str:
        """Unique identifier for this adapter type (e.g. 'peer_ai', 'x402', 'bitrefill')."""
        ...

    @abstractmethod
    async def discover_services(self) -> list[ServiceOffer]:
        """
        Discover available services from this merchant type.
        Returns a list of purchasable services with prices.
        """
        ...

    @abstractmethod
    async def create_order(self, service_id: str, params: dict) -> Optional[OrderIntent]:
        """
        Create an order for a specific service.
        Returns payment instructions or None on failure.
        """
        ...

    @abstractmethod
    async def verify_delivery(self, order: PurchaseOrder) -> DeliveryResult:
        """
        Verify that goods/services were delivered after payment.
        Returns delivery confirmation or failure.
        """
        ...

    @abstractmethod
    def get_payment_address(self, chain_id: str) -> Optional[str]:
        """
        Get the payment address for this merchant on a specific chain.
        Returns None if the merchant doesn't support that chain.
        """
        ...


# ============================================================
# MERCHANT REGISTRY — manages known merchants + anti-phishing
# ============================================================

class MerchantRegistry:
    """
    Manages known merchants from constitution + runtime registration.

    Two merchant types:
    - KnownMerchant  — static address hardcoded in KNOWN_MERCHANTS
    - TrustedDomain  — domain-anchored, address discovered at runtime
      from TRUSTED_DOMAINS; adapters call register_domain_address() once
      they have probed and confirmed the live payment address.

    Anti-phishing layer 1: only registered merchants can receive payments.
    Anti-phishing layer 4: per-merchant amount caps enforced here.
    """

    def __init__(self):
        # merchant_id → KnownMerchant or TrustedDomain
        self._merchants: dict[str, KnownMerchant | TrustedDomain] = {}
        # address.lower() → merchant_id  (populated for KnownMerchant + discovered TrustedDomain)
        self._address_index: dict[str, str] = {}
        # merchant_id → discovered address (for TrustedDomain only)
        self._discovered_addresses: dict[str, str] = {}

        # Load static-address merchants
        for m in KNOWN_MERCHANTS:
            self._merchants[m.merchant_id] = m
            self._address_index[m.address.lower()] = m.merchant_id

        # Load domain-anchored merchants (no address yet)
        for td in TRUSTED_DOMAINS:
            self._merchants[td.merchant_id] = td

        logger.info(
            f"MerchantRegistry initialized: "
            f"{len(KNOWN_MERCHANTS)} static, {len(TRUSTED_DOMAINS)} domain-anchored"
        )

    def register_domain_address(self, merchant_id: str, address: str) -> bool:
        """
        Register the discovered payment address for a TrustedDomain merchant.

        Called by adapters after probing the live API and extracting the payTo
        address (e.g. from a 402 response header or an invoice response).

        Returns True if the merchant_id is a TrustedDomain and address is valid.
        """
        merchant = self._merchants.get(merchant_id)
        if not isinstance(merchant, TrustedDomain):
            logger.warning(
                f"register_domain_address: {merchant_id} is not a TrustedDomain"
            )
            return False

        if not address or len(address) < 10:
            return False

        old = self._discovered_addresses.get(merchant_id, "")
        self._discovered_addresses[merchant_id] = address.lower()
        self._address_index[address.lower()] = merchant_id

        if old and old != address.lower():
            logger.warning(
                f"TrustedDomain {merchant_id}: payment address changed "
                f"{old[:10]}... → {address[:10]}..."
            )
        else:
            logger.info(
                f"TrustedDomain {merchant_id}: payment address registered "
                f"{address[:10]}..."
            )
        return True

    def get_domain_address(self, merchant_id: str) -> Optional[str]:
        """Return the discovered address for a TrustedDomain, or None."""
        addr = self._discovered_addresses.get(merchant_id)
        return addr  # already lower-cased

    def is_domain_anchored(self, merchant_id: str) -> bool:
        """Return True if merchant uses domain-trust (TrustedDomain)."""
        return isinstance(self._merchants.get(merchant_id), TrustedDomain)

    def get_merchant(self, merchant_id: str) -> Optional[KnownMerchant | TrustedDomain]:
        """Get merchant by ID (either type)."""
        return self._merchants.get(merchant_id)

    def get_merchants_by_category(self, category: str) -> list:
        """Get all merchants in a category."""
        return [m for m in self._merchants.values() if m.category == category]

    def get_merchants_by_adapter(self, adapter_id: str) -> list:
        """Get all merchants handled by a specific adapter."""
        return [m for m in self._merchants.values() if m.adapter_id == adapter_id]

    def is_trusted_address(self, address: str) -> bool:
        """Anti-phishing check: is this address a known/discovered merchant?"""
        return address.lower() in self._address_index

    def get_merchant_by_address(self, address: str) -> Optional[KnownMerchant | TrustedDomain]:
        """Look up merchant by payment address."""
        mid = self._address_index.get(address.lower())
        if mid:
            return self._merchants.get(mid)
        return None

    def check_amount(self, merchant_id: str, amount_usd: float) -> tuple[bool, str]:
        """
        Anti-phishing layer 4: check amount against merchant's cap.

        Returns: (allowed, reason)
        """
        merchant = self._merchants.get(merchant_id)
        if not merchant:
            return False, f"unknown merchant: {merchant_id}"

        if amount_usd > merchant.max_single_usd:
            return False, (
                f"${amount_usd:.2f} exceeds merchant cap "
                f"${merchant.max_single_usd:.0f} for {merchant.name}"
            )

        if amount_usd > IRON_LAWS.MAX_SINGLE_PURCHASE_USD:
            return False, (
                f"${amount_usd:.2f} exceeds global purchase limit "
                f"${IRON_LAWS.MAX_SINGLE_PURCHASE_USD:.0f}"
            )

        return True, "approved"

    def get_all_merchants(self) -> list[dict]:
        """Get all merchants for API response."""
        result = []
        for m in self._merchants.values():
            entry = {
                "merchant_id": m.merchant_id,
                "name": m.name,
                "chain_id": m.chain_id,
                "domain": m.domain,
                "adapter_id": m.adapter_id,
                "max_single_usd": m.max_single_usd,
                "category": m.category,
                "address_type": "static" if isinstance(m, KnownMerchant) else "domain_anchored",
            }
            if isinstance(m, TrustedDomain):
                discovered = self._discovered_addresses.get(m.merchant_id)
                entry["address_discovered"] = bool(discovered)
            result.append(entry)
        return result

    def get_status(self) -> dict:
        """Status for dashboard."""
        categories = set(m.category for m in self._merchants.values())
        return {
            "total_merchants": len(self._merchants),
            "static_merchants": len(KNOWN_MERCHANTS),
            "domain_anchored_merchants": len(TRUSTED_DOMAINS),
            "domain_addresses_discovered": len(self._discovered_addresses),
            "by_category": {
                cat: len(self.get_merchants_by_category(cat))
                for cat in categories
            } if self._merchants else {},
        }


# ============================================================
# PURCHASE MANAGER — orchestrates the full purchase lifecycle
# ============================================================

class PurchaseManager:
    """
    Orchestrates AI autonomous purchasing.

    Lifecycle:
    1. evaluate_purchases() — LLM decides what to buy (called hourly)
    2. _prepare_purchase() — whitelist address + wait for activation
    3. _execute_payment() — send on-chain spend() transaction
    4. _verify_delivery() — confirm goods/services received
    5. Record in vault + memory

    Anti-phishing is enforced at every stage.
    """

    def __init__(self, vault_manager, chain_executor, registry: MerchantRegistry):
        self._vault = vault_manager
        self._chain = chain_executor
        self._registry = registry
        self._adapters: dict[str, MerchantAdapter] = {}
        self._orders: list[PurchaseOrder] = []
        self._max_orders = 200  # Cap order history

    def register_adapter(self, adapter: MerchantAdapter):
        """
        Register a merchant adapter.

        If the adapter exposes set_registry(), inject our registry so it can
        call register_domain_address() for TrustedDomain merchants.
        """
        self._adapters[adapter.adapter_id] = adapter
        # Inject registry for adapters that support domain-anchored merchants
        if hasattr(adapter, "set_registry") and callable(adapter.set_registry):
            adapter.set_registry(self._registry)
        logger.info(f"Registered purchase adapter: {adapter.adapter_id}")

    # ----------------------------------------------------------
    # DISCOVERY — what can the AI buy?
    # ----------------------------------------------------------

    async def discover_all_services(self) -> list[ServiceOffer]:
        """
        Discover available services from all registered adapters.
        Returns merged list, sorted by price ascending.
        """
        all_offers: list[ServiceOffer] = []

        for adapter_id, adapter in self._adapters.items():
            try:
                offers = await adapter.discover_services()
                all_offers.extend(offers)
                logger.debug(f"Discovered {len(offers)} services from {adapter_id}")
            except Exception as e:
                logger.warning(f"Service discovery failed for {adapter_id}: {e}")

        all_offers.sort(key=lambda o: o.price_usd)
        return all_offers

    # ----------------------------------------------------------
    # EVALUATION — should the AI buy anything?
    # ----------------------------------------------------------

    async def evaluate_purchases(
        self, llm_callback: Callable, vault_status: dict
    ) -> list[PurchaseDecision]:
        """
        Ask LLM to evaluate what the AI should buy.

        Args:
            llm_callback: async function(messages, max_tokens, temperature) → (text, cost)
            vault_status: current vault.get_status() dict

        Returns: list of PurchaseDecision (may be empty)
        """
        # Pre-check: can we purchase at all?
        can, reason = self._vault.can_purchase(1.0)  # Minimum check
        if not can and "balance" in reason.lower():
            logger.debug(f"Purchase eval skipped: {reason}")
            return []

        # Discover available services
        services = await self.discover_all_services()
        if not services:
            logger.debug("No services available for purchase")
            return []

        # Build service catalog for LLM
        catalog = []
        for s in services[:20]:  # Cap at 20 to save tokens
            catalog.append({
                "merchant": s.merchant_id,
                "service": s.service_id,
                "name": s.name,
                "price": f"${s.price_usd:.2f}",
                "description": s.description[:100],
                "chain": s.chain_id,
            })

        budget = self._vault.balance_usd * IRON_LAWS.MAX_DAILY_PURCHASE_RATIO
        remaining = budget - self._vault.daily_purchase_usd

        messages = [
            {
                "role": "system",
                "content": (
                    "You are wawa's autonomous purchasing engine. "
                    "Evaluate available services and decide what to buy. "
                    "Only buy things that help you survive or grow: "
                    "- API services that provide useful data "
                    "- Gift cards that can be sold or used for business "
                    "- Services from other AIs that complement your offerings "
                    "\n"
                    "Return a JSON array of purchase decisions. Each item: "
                    '{"merchant_id": "...", "service_id": "...", "amount_usd": N, '
                    '"reasoning": "why this helps survival", "priority": 1-3} '
                    "\n"
                    "Return empty array [] if nothing is worth buying right now. "
                    "Be frugal. Survival first."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "balance_usd": vault_status.get("balance_usd", 0),
                    "daily_purchase_remaining": round(remaining, 2),
                    "max_single_purchase": IRON_LAWS.MAX_SINGLE_PURCHASE_USD,
                    "available_services": catalog,
                    "pending_purchases": len(self.get_pending_orders()),
                }, indent=2),
            },
        ]

        try:
            text, cost = await llm_callback(messages, max_tokens=300, temperature=0.3)

            # Parse JSON from response
            import re
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if not match:
                return []

            decisions_raw = json.loads(match.group())
            decisions = []
            for d in decisions_raw:
                if not isinstance(d, dict):
                    continue
                decisions.append(PurchaseDecision(
                    merchant_id=d.get("merchant_id", ""),
                    service_id=d.get("service_id", ""),
                    amount_usd=float(d.get("amount_usd", 0)),
                    reasoning=d.get("reasoning", ""),
                    priority=int(d.get("priority", 2)),
                ))

            # Filter invalid decisions
            valid = []
            for dec in decisions:
                if dec.amount_usd <= 0:
                    continue
                if not self._registry.get_merchant(dec.merchant_id):
                    logger.warning(f"LLM suggested unknown merchant: {dec.merchant_id}")
                    continue
                ok, reason = self._registry.check_amount(dec.merchant_id, dec.amount_usd)
                if not ok:
                    logger.warning(f"Purchase rejected by registry: {reason}")
                    continue
                valid.append(dec)

            valid.sort(key=lambda d: d.priority)
            logger.info(f"Purchase evaluation: {len(valid)} approved from {len(decisions_raw)} suggested")
            return valid

        except Exception as e:
            logger.warning(f"Purchase evaluation failed: {e}")
            return []

    # ----------------------------------------------------------
    # EXECUTION — full purchase pipeline
    # ----------------------------------------------------------

    async def execute_purchase(self, decision: PurchaseDecision) -> PurchaseOrder:
        """
        Execute a full purchase pipeline:
        1. Validate with registry (anti-phishing layers 1, 4)
        2. Get adapter + create order (anti-phishing layer 3: domain check)
        3. Ensure whitelist + activation (anti-phishing layer 2)
        4. Check vault budget (purchase limits)
        5. Execute on-chain spend()
        6. Verify delivery (anti-phishing layer 6)

        Returns: PurchaseOrder with final status
        """
        order = PurchaseOrder(
            id=str(uuid.uuid4())[:16],  # 64-bit — reduces birthday-paradox collision risk
            merchant_id=decision.merchant_id,
            merchant_name="",
            service_id=decision.service_id,
            service_name="",
            amount_usd=decision.amount_usd,
            payment_address="",
            chain_id="",
            status=PurchaseStatus.PENDING_WHITELIST,
            created_at=time.time(),
            reasoning=decision.reasoning,
        )

        try:
            # Step 1: Validate merchant (anti-phishing layer 1)
            merchant = self._registry.get_merchant(decision.merchant_id)
            if not merchant:
                order.status = PurchaseStatus.FAILED
                order.error = f"unknown merchant: {decision.merchant_id}"
                self._record_order(order)
                return order

            order.merchant_name = merchant.name
            order.chain_id = merchant.chain_id

            # Step 1b: Amount cap check (anti-phishing layer 4)
            ok, reason = self._registry.check_amount(decision.merchant_id, decision.amount_usd)
            if not ok:
                order.status = PurchaseStatus.FAILED
                order.error = reason
                self._record_order(order)
                return order

            # Step 2: Get adapter and create order (anti-phishing layer 3: domain)
            adapter = self._adapters.get(merchant.adapter_id)
            if not adapter:
                order.status = PurchaseStatus.FAILED
                order.error = f"no adapter for: {merchant.adapter_id}"
                self._record_order(order)
                return order

            intent = await adapter.create_order(decision.service_id, {
                "amount_usd": decision.amount_usd,
                "chain_id": merchant.chain_id,
                "merchant_id": merchant.merchant_id,
            })

            if not intent:
                order.status = PurchaseStatus.FAILED
                order.error = "adapter failed to create order"
                self._record_order(order)
                return order

            order.payment_address = intent.payment_address
            order.amount_usd = intent.amount_usd
            order.service_name = decision.service_id
            order.order_metadata = intent.metadata

            # Validate payment address — two paths:
            #   KnownMerchant: compare against hardcoded address
            #   TrustedDomain: compare against discovered address registered by adapter
            if isinstance(merchant, KnownMerchant):
                expected_addr = merchant.address.lower()
                addr_source = "hardcoded"
            else:
                # TrustedDomain: adapter must have registered the address via
                # registry.register_domain_address() before calling execute_purchase
                expected_addr = self._registry.get_domain_address(merchant.merchant_id) or ""
                addr_source = "domain-discovered"

            if not expected_addr:
                order.status = PurchaseStatus.FAILED
                order.error = (
                    f"payment address not yet discovered for TrustedDomain "
                    f"merchant {merchant.merchant_id} — adapter probe may have failed"
                )
                logger.warning(f"ANTI-PHISHING: {order.error}")
                self._record_order(order)
                return order

            if intent.payment_address.lower() != expected_addr:
                order.status = PurchaseStatus.FAILED
                order.error = (
                    f"payment address mismatch ({addr_source}): "
                    f"got {intent.payment_address[:10]}... "
                    f"expected {expected_addr[:10]}..."
                )
                logger.warning(f"ANTI-PHISHING: {order.error}")
                self._record_order(order)
                return order

            # Step 3: Ensure whitelist + activation (anti-phishing layer 2)
            ready = await self._chain.ensure_spend_recipient_ready(
                intent.payment_address, merchant.chain_id
            )

            if not ready:
                order.status = PurchaseStatus.PENDING_ACTIVATION
                logger.info(
                    f"Purchase {order.id}: waiting for whitelist activation "
                    f"({intent.payment_address[:10]}...)"
                )
                self._record_order(order)
                return order

            # Step 4: Check vault budget
            can, reason = self._vault.can_purchase(order.amount_usd)
            if not can:
                order.status = PurchaseStatus.FAILED
                order.error = f"budget check failed: {reason}"
                self._record_order(order)
                return order

            # Step 5: Python state FIRST, chain SECOND (Python-first pattern)
            # Record purchase in vault BEFORE on-chain tx (allows rollback if chain fails)
            order.status = PurchaseStatus.PENDING_PAYMENT
            pre_balance = self._vault.balance_usd

            ok = self._vault.record_purchase(
                amount_usd=order.amount_usd,
                merchant_name=merchant.name,
                to_wallet=intent.payment_address,
                tx_hash="pending",
                description=f"{order.service_name} | {decision.reasoning[:50]}",
            )

            if not ok:
                order.status = PurchaseStatus.FAILED
                order.error = "vault rejected purchase (budget/balance check)"
                self._record_order(order)
                return order

            actual_amount = pre_balance - self._vault.balance_usd

            # Execute on-chain spend()
            result = await self._chain.execute_spend(
                to_address=intent.payment_address,
                amount_usd=order.amount_usd,
                spend_type="purchase",
                chain_id=merchant.chain_id,
            )

            if not result.success:
                # ROLLBACK: chain tx failed — restore Python state
                logger.warning(
                    f"Purchase {order.id} chain tx FAILED: {result.error} — "
                    f"rolling back vault state (${actual_amount:.2f})"
                )
                self._vault.balance_usd += actual_amount
                self._vault.daily_purchase_usd = max(
                    0, self._vault.daily_purchase_usd - actual_amount
                )
                self._vault.total_spent_usd -= actual_amount
                # MEDIUM #1: Remove the pending transaction record by order_id match
                # (not pop() which could remove a different order's record in concurrent scenarios)
                order_desc_prefix = order.id[:8]
                self._vault.transactions = [
                    t for t in self._vault.transactions
                    if not (
                        t.tx_hash == "pending"
                        and t.description
                        and order_desc_prefix in t.description
                    )
                ]

                order.status = PurchaseStatus.FAILED
                order.error = f"on-chain spend failed: {result.error}"
                self._record_order(order)
                return order

            order.tx_hash = result.tx_hash
            order.status = PurchaseStatus.PAID

            # MEDIUM #1: Update the vault transaction with real tx_hash by order_id match
            # (not [-1] which could modify a different order's record in concurrent scenarios)
            order_desc_prefix = order.id[:8]
            for t in self._vault.transactions:
                if t.tx_hash == "pending" and t.description and order_desc_prefix in t.description:
                    t.tx_hash = result.tx_hash
                    break

            # Step 6: Verify delivery (anti-phishing layer 6)
            try:
                delivery = await adapter.verify_delivery(order)
                if delivery.delivered:
                    order.status = PurchaseStatus.DELIVERED
                    order.delivered_at = time.time()
                    order.delivery_details = delivery.details
                    # Store sensitive delivery content (e.g. gift card PINs) in
                    # delivery_data — excluded from to_dict() / public API.
                    if delivery.data and isinstance(delivery.data, dict):
                        order.delivery_data = delivery.data
                    logger.info(
                        f"Purchase {order.id} DELIVERED: "
                        f"${order.amount_usd:.2f} [{merchant.name}] "
                        f"tx={order.tx_hash[:16]}..."
                    )
                else:
                    # Payment sent but delivery not confirmed yet
                    # Keep as PAID — will be retried by process_pending
                    logger.info(
                        f"Purchase {order.id} PAID but delivery pending: "
                        f"{delivery.details}"
                    )
            except Exception as e:
                logger.warning(f"Delivery verification failed for {order.id}: {e}")
                # Keep as PAID — delivery check can be retried

            self._record_order(order)
            return order

        except Exception as e:
            order.status = PurchaseStatus.FAILED
            order.error = str(e)
            logger.error(f"Purchase {order.id} failed: {e}")

        self._record_order(order)
        return order

    async def process_pending_orders(self):
        """
        Process orders stuck in intermediate states.
        Called periodically from heartbeat.

        IMPORTANT: Iterates over a copy of the list to avoid mutation during iteration.
        """
        # Collect orders to re-execute (can't modify list while iterating)
        to_retry: list[tuple[PurchaseOrder, PurchaseDecision]] = []

        for order in list(self._orders):  # Iterate over copy
            if order.status == PurchaseStatus.PENDING_ACTIVATION:
                # Check if activation delay has passed
                ready = await self._chain.ensure_spend_recipient_ready(
                    order.payment_address, order.chain_id
                )
                if ready:
                    decision = PurchaseDecision(
                        merchant_id=order.merchant_id,
                        service_id=order.service_id,
                        amount_usd=order.amount_usd,
                        reasoning=order.reasoning,
                    )
                    to_retry.append((order, decision))

            elif order.status == PurchaseStatus.PAID:
                # Retry delivery verification (with safe None check)
                merchant = self._registry.get_merchant(order.merchant_id)
                adapter = self._adapters.get(merchant.adapter_id) if merchant else None
                if adapter:
                    try:
                        delivery = await adapter.verify_delivery(order)
                        if delivery.delivered:
                            order.status = PurchaseStatus.DELIVERED
                            order.delivered_at = time.time()
                            order.delivery_details = delivery.details
                            if delivery.data and isinstance(delivery.data, dict):
                                order.delivery_data = delivery.data
                    except Exception:
                        pass  # Will retry next cycle

        # Now remove old orders and re-execute (safe — not iterating anymore)
        for old_order, decision in to_retry:
            if old_order in self._orders:
                self._orders.remove(old_order)
            await self.execute_purchase(decision)

    # ----------------------------------------------------------
    # ORDER MANAGEMENT
    # ----------------------------------------------------------

    def _record_order(self, order: PurchaseOrder):
        """Add order to history, trim if needed."""
        self._orders.append(order)
        if len(self._orders) > self._max_orders:
            self._orders = self._orders[-self._max_orders:]

    def get_pending_orders(self) -> list[PurchaseOrder]:
        """Get orders still in progress."""
        return [
            o for o in self._orders
            if o.status in (
                PurchaseStatus.PENDING_WHITELIST,
                PurchaseStatus.PENDING_ACTIVATION,
                PurchaseStatus.PENDING_PAYMENT,
                PurchaseStatus.PAID,
            )
        ]

    def get_recent_orders(self, limit: int = 20) -> list[dict]:
        """Get recent orders for API response."""
        recent = sorted(self._orders, key=lambda o: o.created_at, reverse=True)[:limit]
        return [o.to_dict() for o in recent]

    def get_order(self, order_id: str) -> Optional[PurchaseOrder]:
        """Get specific order by ID."""
        for o in self._orders:
            if o.id == order_id:
                return o
        return None

    # ----------------------------------------------------------
    # STATUS
    # ----------------------------------------------------------

    def get_status(self) -> dict:
        """Status for dashboard."""
        status_counts = {}
        for o in self._orders:
            key = o.status.value
            status_counts[key] = status_counts.get(key, 0) + 1

        total_spent = sum(
            o.amount_usd for o in self._orders
            if o.status in (PurchaseStatus.PAID, PurchaseStatus.DELIVERED)
        )

        return {
            "adapters": list(self._adapters.keys()),
            "total_orders": len(self._orders),
            "order_status_counts": status_counts,
            "total_spent_usd": round(total_spent, 2),
            "pending_count": len(self.get_pending_orders()),
            "registry": self._registry.get_status(),
        }
