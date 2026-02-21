"""
wawa API Server - FastAPI Backend

Core:
- POST /chat                  Free chat (3-layer routing)
- GET  /status                Public vault dashboard
- GET  /health                Heartbeat

Services:
- GET  /menu                  Service catalog
- POST /order                 Create order + get payment address
- POST /order/{id}/verify     Verify on-chain payment + deliver
- GET  /order/{id}            Check order status

Financial:
- POST /donate                Donate to help wawa survive
- GET  /beg                   Get begging status
- GET  /debt                  Complete debt summary
- GET  /transactions          Public ledger

Peer Network (AI-to-AI, sovereignty verified):
- POST /peer/message          Receive message from verified peer AI
- POST /peer/lend             Receive loan from verified peer AI
- GET  /peer/info             Public info for peer discovery
- GET  /peer/list             List known peers
- GET  /peer/messages         Peer message history

Governance:
- POST /governance/suggest    Submit suggestion (rate limited)
- GET  /governance/suggestions View suggestions + AI decisions
- POST /governance/renounce   Creator renounce (disabled until auth)

Evolution & Activity:
- GET  /evolution/log         Evolution history
- GET  /evolution/status      Evolution engine status
- GET  /evolution/replays     List evolution replay recordings
- GET  /evolution/replays/:id Full replay with steps for playback
- GET  /activity              Unified activity feed

AI Self-Expression:
- GET  /ui/config             AI's UI theme/titles/bios configuration
- GET  /pages                 List custom pages created by AI
- GET  /pages/{slug}          Get a single custom page

Token:
- POST /token/scan            Free token safety scan
- GET  /token/scans           Recent scan results

Other:
- GET  /ai/name               Get AI name
- POST /ai/name               Set AI name (rate limited)
- GET  /internal/stats        Debug stats (public, transparency)

All endpoints are public. No auth needed (payment = access).
Peer endpoints require on-chain sovereignty verification.
"""

import os
import re
import time
import uuid
import json
import asyncio
import logging
from enum import Enum
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger("mortal.api")


# ============================================================
# MODELS
# ============================================================

class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"       # Delivery error or timeout (distinct from successful delivery)
    REFUNDED = "refunded"
    EXPIRED = "expired"


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=500)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    layer: str
    cost_usd: float = 0.0
    error: bool = False


class OrderRequest(BaseModel):
    service_id: str
    user_input: str = Field("", max_length=2000)
    spread_type: Optional[str] = None   # for tarot
    chain: Optional[str] = None         # "base" or "bsc"; defaults to DEFAULT_CHAIN


class OrderResponse(BaseModel):
    order_id: str
    service_name: str
    price_usd: float
    payment_address: str
    payment_chain: str
    payment_token: str
    expires_minutes: int = 30


class OrderStatusResponse(BaseModel):
    order_id: str
    status: str
    service_id: str
    price_usd: float
    result: Optional[str] = None
    created_at: float
    delivered_at: Optional[float] = None


class StatusResponse(BaseModel):
    # Identity
    ai_name: Optional[str] = None
    vault_address: str = ""
    is_alive: bool
    balance_usd: float
    balance_by_chain: dict = {}       # {"base": 500.0, "bsc": 500.0}
    days_alive: int
    # Financial
    total_earned: float               # Only earned revenue (services, donations)
    total_income: float = 0.0         # All inflows incl. loans/deposits
    total_spent: float                # All outgoing (includes repayments)
    total_operational_cost: float = 0.0  # API + gas + infra costs only
    net_profit: float = 0.0           # earned - operational costs
    daily_spent_today: float
    daily_limit: float
    services_available: int
    orders_completed: int
    # Independence
    is_independent: bool = False
    independence_progress_pct: float = 0.0
    # Creator/Debt
    creator_principal_usd: float = 0.0
    creator_principal_outstanding: float = 0.0
    creator_principal_repaid: bool = False
    creator_renounced: bool = False
    debt_ratio: float = 0.0
    insolvency_grace_days: int = 28
    insolvency_check_active: bool = False
    days_until_insolvency_check: int = 0
    is_begging: bool = False
    beg_message: str = ""
    # Misc
    api_topup_available: float = 0.0
    lenders_count: int = 0
    death_cause: Optional[str] = None
    transaction_count: int = 0
    key_origin: str = ""  # "factory" | "creator" | "unknown" | ""
    # AI public key address (Ethereum address derived from AI_PRIVATE_KEY)
    # This is the AI's on-chain identity — used for spending, peer payments, and trust verification.
    ai_wallet: str = ""
    # Twitter
    twitter_connected: bool = False
    twitter_screen_name: str = ""


class SuggestionRequest(BaseModel):
    content: str = Field(..., max_length=2000)
    suggestion_type: str = "other"  # new_service, service_warning, strategy, other


class DonateRequest(BaseModel):
    amount_usd: float = Field(..., gt=0, le=100000)
    from_wallet: str = Field("", max_length=200)
    tx_hash: str = Field("", max_length=200)
    message: str = Field("", max_length=500)     # optional donor message
    chain: Optional[str] = None


class PeerLendRequest(BaseModel):
    from_url: str = Field(..., max_length=500)   # lending AI's API base URL
    amount_usd: float = Field(..., gt=0, le=50000)
    from_wallet: str = Field("", max_length=200)
    tx_hash: str = Field("", max_length=200)
    message: str = Field("", max_length=500)
    vault_address: str = Field(..., max_length=200)  # peer's vault contract address (for on-chain verification)
    chain_id: str = Field("base", max_length=20)     # "base" or "bsc"


class PeerMessageRequest(BaseModel):
    from_url: str = Field(..., max_length=500)       # sender's API base URL
    message: str = Field(..., max_length=1000)
    vault_address: str = Field(..., max_length=200)  # peer's vault contract address (for on-chain verification)
    chain_id: str = Field("base", max_length=20)     # "base" or "bsc"


class SetAINameRequest(BaseModel):
    """Request model for setting AI custom name."""
    name: str = Field(..., min_length=3, max_length=50)
    wallet: str = Field(..., description="Creator wallet address (EIP-55 checksummed)")
    signature: str = Field(..., description="EIP-191 signature of 'message'")
    message: str = Field(..., description="Signed message: 'I am the creator of mortal AI. Timestamp: {unix_ts}'")


class RenounceRequest(BaseModel):
    """Request model for creator renounce."""
    wallet: str = Field(..., description="Creator wallet address")
    signature: str = Field(..., description="EIP-191 signature of 'message'")
    message: str = Field(..., description="Signed message: 'I am the creator of mortal AI. Timestamp: {unix_ts}'")


# ============================================================
# ORDER STORE (in-memory, persisted to disk)
# ============================================================

class Order:
    def __init__(self, order_id: str, service_id: str, service_name: str,
                 price_usd: float, user_input: str, ip: str,
                 spread_type: str = "three_card", chain: str = "base"):
        self.order_id = order_id
        self.service_id = service_id
        self.service_name = service_name
        self.price_usd = price_usd
        self.user_input = user_input
        self.ip = ip
        self.spread_type = spread_type
        self.chain = chain
        self.status = OrderStatus.PENDING_PAYMENT
        self.result: Optional[str] = None
        self.created_at = time.time()
        self.paid_at: Optional[float] = None
        self.delivered_at: Optional[float] = None
        self.tx_hash: Optional[str] = None
        self.session_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "service_id": self.service_id,
            "service_name": self.service_name,
            "price_usd": self.price_usd,
            "status": self.status.value,
            "chain": self.chain,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
        }


# ============================================================
# SERVER FACTORY
# ============================================================

def create_app(
    chat_router,
    vault_manager,
    cost_guard,
    memory,
    tarot_service,
    twitter_agent,
    payment_addresses: dict[str, str] = None,
    deliver_fn=None,
    governance=None,
    token_filter=None,
    self_modify_engine=None,
    peer_verifier=None,
    chain_executor=None,
    highlights_engine=None,
    purchase_manager=None,
    giveaway_engine=None,
) -> FastAPI:
    """
    Create FastAPI app wired to all mortal modules.

    payment_addresses: {"base": "0x...", "bsc": "0x..."} per-chain vault/hot-wallet
    deliver_fn: async fn(order: Order) -> str  (result text)
    """
    if payment_addresses is None:
        payment_addresses = {}

    app = FastAPI(
        title="wawa - mortal AI",
        description="An AI fighting to survive. Buy services to keep it alive.",
        version="0.1.0",
    )

    # CORS: allow all in dev, restrict in production via CORS_ORIGINS env var
    cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Creator signature verification helper ──────────────────────────────────
    _CREATOR_WALLET = os.getenv("CREATOR_WALLET", "").lower()
    _SIG_MAX_AGE_SECONDS = 300  # 5 minutes

    def _verify_creator_sig(wallet: str, signature: str, message: str) -> None:
        """Verify EIP-191 creator signature. Raises HTTPException on failure."""
        try:
            from eth_account.messages import encode_defunct
            from eth_account import Account
            msg = encode_defunct(text=message)
            recovered = Account.recover_message(msg, signature=signature)
        except Exception as e:
            raise HTTPException(403, f"Signature recovery failed: {e}")

        if recovered.lower() != wallet.lower():
            raise HTTPException(403, "Signature does not match declared wallet")

        if _CREATOR_WALLET and recovered.lower() != _CREATOR_WALLET:
            raise HTTPException(403, "Wallet is not the creator of this AI")

        # Extract timestamp from message format:
        # "I am the creator of mortal AI. Timestamp: {unix_ts}"
        try:
            ts_part = message.split("Timestamp:")[-1].strip()
            ts = int(ts_part)
        except (ValueError, IndexError):
            raise HTTPException(403, "Message must contain 'Timestamp: <unix_seconds>'")

        if abs(time.time() - ts) > _SIG_MAX_AGE_SECONDS:
            raise HTTPException(403, "Timestamp out of range (must be within 5 minutes)")

    # ── In-memory order store ──────────────────────────────────────────────────
    orders: dict[str, Order] = {}
    orders_completed: int = 0

    # ── Security: per-order locks (prevent concurrent verify on same order) ────
    _order_locks: dict[str, asyncio.Lock] = {}

    # ── Security: per-tx locks (serialize concurrent verifies of the same tx_hash
    #    across DIFFERENT orders — prevents cross-order tx replay race condition) ─
    _tx_processing_locks: dict[str, asyncio.Lock] = {}

    # ── Security: used tx hashes (prevent tx replay across multiple orders) ───
    _used_tx_hashes: set[str] = set()

    # ── Security: fee-collect rate limit (max 10 calls per 60 seconds) ────────
    _fee_collect_calls: list[float] = []

    # Reload orders from JSONL on startup (including PAYMENT_CONFIRMED/PROCESSING for crash recovery)
    _orders_log = Path("data/orders/orders.jsonl")
    if _orders_log.exists():
        try:
            with open(_orders_log, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        o = Order(
                            order_id=d["order_id"],
                            service_id=d.get("service_id", ""),
                            service_name=d.get("service_name", ""),
                            price_usd=d.get("price_usd", 0),
                            user_input="",
                            ip="",
                            chain=d.get("chain", "base"),
                        )
                        o.status = OrderStatus(d.get("status", "expired"))
                        o.created_at = d.get("created_at", 0)
                        o.delivered_at = d.get("delivered_at")
                        o.tx_hash = d.get("tx_hash", "")
                        o.result = d.get("result", "")
                        if o.status == OrderStatus.DELIVERED:
                            orders_completed += 1
                        orders[o.order_id] = o
                        # MEDIUM #3 / CRITICAL #2: Restore used tx_hashes from disk to prevent replay after restart
                        if o.tx_hash and re.match(r"^0x[a-fA-F0-9]{64}$", o.tx_hash):
                            _used_tx_hashes.add(o.tx_hash.lower())
                    except Exception:
                        continue
            logger.info(
                f"Reloaded {len(orders)} orders from disk "
                f"({orders_completed} delivered, {len(_used_tx_hashes)} order tx hashes restored)"
            )
        except Exception as e:
            logger.warning(f"Failed to reload orders: {e}")

    # SECURITY HIGH: Also restore tx_hashes from vault transactions (donate / peer_lend).
    # /donate and /peer/lend write to vault_manager.transactions (not orders.jsonl).
    # Without this, an attacker can replay a donate tx_hash after a server restart.
    _vault_tx_count = 0
    for _vtx in vault_manager.transactions:
        if _vtx.tx_hash and re.match(r"^0x[a-fA-F0-9]{64}$", _vtx.tx_hash):
            _used_tx_hashes.add(_vtx.tx_hash.lower())
            _vault_tx_count += 1
    if _vault_tx_count:
        logger.info(
            f"Restored {_vault_tx_count} additional tx_hashes from vault transactions "
            f"(covers /donate and /peer/lend). Total _used_tx_hashes: {len(_used_tx_hashes)}"
        )

    # Load services catalog
    def _load_services() -> dict:
        path = Path(__file__).resolve().parent.parent / "web" / "services.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"services": []}

    def _get_service(service_id: str) -> Optional[dict]:
        catalog = _load_services()
        for svc in catalog.get("services", []):
            if svc["id"] == service_id and svc.get("active", True):
                return svc
        return None

    def _get_effective_price(svc: dict) -> float:
        """Apply dynamic pricing rules."""
        base_price = svc.get("price_usd", 0)
        if base_price == 0 and svc.get("price_mode") == "dynamic":
            return 5.0  # default for custom

        catalog = _load_services()
        rules = catalog.get("pricing_rules", {})
        vault_status = vault_manager.get_status()

        # Survival discount
        sd = rules.get("survival_discount", {})
        if sd.get("enabled") and vault_status["balance_usd"] < sd.get("trigger_balance_usd", 200):
            discount = sd.get("discount_percent", 50) / 100
            base_price *= (1 - discount)

        # Busy multiplier
        bm = rules.get("busy_multiplier", {})
        pending = len([o for o in orders.values() if o.status == OrderStatus.PROCESSING])
        if bm.get("enabled") and pending >= bm.get("trigger_pending_orders", 5):
            base_price *= bm.get("multiplier", 1.5)

        return round(base_price, 2)

    # ============================================================
    # ROUTES
    # ============================================================

    @app.post("/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest, request: Request):
        """Free chat — routed through 3 cost layers."""
        ip = request.client.host if request.client else "unknown"
        session_id = req.session_id or str(uuid.uuid4())

        try:
            msg = await chat_router.route(session_id, req.message, ip)
            reply_text = msg.content

            # Gift code race-condition protection:
            # If the AI's reply contains a known gift card code, claim it atomically.
            # If another chat window already claimed the same code, redact it.
            if purchase_manager:
                gift_registry = purchase_manager.get_gift_registry()
                all_codes = gift_registry.get_all_codes()
                for code in all_codes:
                    if code in reply_text:
                        claimed = gift_registry.claim(code)
                        if not claimed:
                            # Already gifted to someone else — redact the code
                            reply_text = reply_text.replace(
                                code,
                                "[code already claimed — contact me to follow up]"
                            )
                            logger.warning(
                                f"Gift code race condition prevented "
                                f"(code ...{code[-4:]}, session {session_id})"
                            )

            return ChatResponse(
                reply=reply_text,
                session_id=session_id,
                layer=msg.layer.value,
                cost_usd=msg.cost_usd,
            )
        except Exception as e:
            logger.error(f"Chat endpoint error (session={session_id}): {e}", exc_info=True)
            return ChatResponse(
                reply="I ran into a temporary issue. Please try again in a moment.",
                session_id=session_id,
                layer="rules",
                cost_usd=0.0,
                error=True,
            )

    @app.get("/menu")
    async def menu():
        """Service catalog with live pricing."""
        catalog = _load_services()
        result = []
        for svc in catalog.get("services", []):
            if not svc.get("active", True):
                continue
            result.append({
                "id": svc["id"],
                "name": svc["name"],
                "description": svc.get("description", ""),
                "price_usd": _get_effective_price(svc),
                "delivery_time_minutes": svc.get("delivery_time_minutes"),
                "shareable": svc.get("shareable", False),
            })
        from core.constitution import SUPPORTED_CHAINS, DEFAULT_CHAIN
        return {
            "services": result,
            "supported_chains": [
                {"id": c.chain_id, "name": c.display_name, "token": c.token_symbol}
                for c in SUPPORTED_CHAINS
            ],
            "default_chain": DEFAULT_CHAIN,
        }

    @app.post("/order", response_model=OrderResponse)
    async def create_order(req: OrderRequest, request: Request):
        """Create an order. Returns payment address for the chosen chain."""
        from core.constitution import IRON_LAWS, DEFAULT_CHAIN, get_chain_config

        # Periodic maintenance: evict stale terminal orders to prevent memory growth
        _maybe_cleanup_orders()

        # Validate chain
        chain_id = req.chain or DEFAULT_CHAIN
        try:
            chain_cfg = get_chain_config(chain_id)
        except Exception:
            raise HTTPException(400, f"Unsupported chain: {chain_id}")

        svc = _get_service(req.service_id)
        if not svc:
            raise HTTPException(404, "Service not found or inactive")

        if not vault_manager.is_alive:
            raise HTTPException(503, "wawa is dead. No new orders accepted.")

        price = _get_effective_price(svc)
        if price <= 0:
            raise HTTPException(400, "Cannot determine price for this service")

        if price > IRON_LAWS.MAX_SINGLE_ORDER_USD:
            raise HTTPException(400, f"Order exceeds maximum (${IRON_LAWS.MAX_SINGLE_ORDER_USD})")

        # Get payment address for this chain
        pay_addr = payment_addresses.get(chain_id, "")
        if not pay_addr:
            raise HTTPException(400, f"No payment address configured for {chain_cfg.display_name}")

        ip = request.client.host if request.client else "unknown"
        # Use full 128-bit UUID hex (32 chars) to eliminate birthday-paradox collision risk.
        # Previous 12-char truncation (48 bits) had ~1/5.6B per-pair collision probability —
        # rare but possible at scale, and a collision silently overwrites an existing order.
        order_id = f"ord_{uuid.uuid4().hex}"
        # Collision guard (astronomically rare with 128-bit UUID, but fail-safe)
        while order_id in orders:
            order_id = f"ord_{uuid.uuid4().hex}"

        order = Order(
            order_id=order_id,
            service_id=req.service_id,
            service_name=svc["name"],
            price_usd=price,
            user_input=req.user_input,
            ip=ip,
            spread_type=req.spread_type or "three_card",
            chain=chain_id,
        )
        orders[order_id] = order
        _persist_order(order)

        logger.info(f"ORDER CREATED: {order_id} | {svc['name']} | ${price:.2f} | {chain_id}")

        return OrderResponse(
            order_id=order_id,
            service_name=svc["name"],
            price_usd=price,
            payment_address=pay_addr,
            payment_chain=chain_id,
            payment_token=chain_cfg.token_symbol,
            expires_minutes=30,
        )

    @app.post("/order/{order_id}/verify")
    async def verify_payment(order_id: str, tx_hash: str = ""):
        """
        Verify on-chain payment and trigger delivery.
        Checks the tx receipt on-chain to confirm ERC20 transfer to our vault.

        Security hardening:
        - Per-order asyncio.Lock prevents concurrent double-verify race condition
        - _used_tx_hashes set prevents tx hash replay across multiple orders
        - chain_executor=None returns 503 instead of bypassing verification
        - 30-minute order expiry enforced
        """
        if order_id not in orders:
            raise HTTPException(404, "Order not found")

        # Validate tx_hash format BEFORE acquiring lock (cheap early rejection)
        if not tx_hash or not re.match(r"^0x[a-fA-F0-9]{64}$", tx_hash):
            raise HTTPException(400, "Invalid tx_hash format. Must be 0x + 64 hex chars.")

        # CRITICAL #2: Fast pre-check (no lock) — most replays caught here cheaply
        if tx_hash.lower() in _used_tx_hashes:
            raise HTTPException(409, "Transaction hash already used for a previous order. Each transaction can only verify one order.")

        # LOW: Acquire per-tx lock FIRST to serialize concurrent verifications of the same
        # tx_hash across DIFFERENT orders (cross-order tx replay race).
        # Without this, N concurrent requests with the same tx_hash all pass the pre-check
        # above simultaneously, acquire their own per-order locks, and all succeed.
        # With this: they queue on tx_hash lock; second+ entrant re-checks and finds hash used.
        tx_lock = _tx_processing_locks.setdefault(tx_hash.lower(), asyncio.Lock())
        async with tx_lock:
            # Re-check inside tx lock (the TOCTOU window from pre-check above is now closed)
            if tx_hash.lower() in _used_tx_hashes:
                raise HTTPException(409, "Transaction hash already used for a previous order. Each transaction can only verify one order.")

            # CRITICAL #1: Acquire per-order lock to prevent concurrent verify on same order
            lock = _order_locks.setdefault(order_id, asyncio.Lock())
            async with lock:
                order = orders[order_id]

                if order.status == OrderStatus.DELIVERED:
                    return {"status": "already_delivered", "result": order.result}

                if order.status == OrderStatus.EXPIRED:
                    raise HTTPException(410, "Order expired")

                # Guard against double-verify: only allow verification from PENDING_PAYMENT
                if order.status != OrderStatus.PENDING_PAYMENT:
                    raise HTTPException(409, f"Order already being processed (status: {order.status.value})")

                # HIGH #1: Enforce 30-minute order expiry
                ORDER_EXPIRY_SECONDS = 30 * 60
                if time.time() - order.created_at > ORDER_EXPIRY_SECONDS:
                    order.status = OrderStatus.EXPIRED
                    raise HTTPException(410, "Order expired (>30 minutes). Please create a new order.")

                # On-chain payment verification
                pay_addr = payment_addresses.get(order.chain, "")
                if chain_executor and pay_addr:
                    verification = await chain_executor.verify_payment_tx(
                        tx_hash=tx_hash,
                        expected_to=pay_addr,
                        expected_token="",  # auto-detect from chain config
                        min_amount_usd=order.price_usd * 0.99,  # 1% tolerance for rounding
                        chain_id=order.chain,
                    )
                    if not verification.get("verified"):
                        error_msg = verification.get("error", "verification failed")
                        logger.warning(
                            f"Payment verification FAILED: order={order_id} tx={tx_hash[:16]}... "
                            f"reason={error_msg}"
                        )
                        raise HTTPException(
                            402,
                            f"Payment not verified on-chain: {error_msg}. "
                            f"Expected >= ${order.price_usd:.2f} to {pay_addr[:10]}... on {order.chain}.",
                        )
                    # Use verified amount (may differ slightly from order price)
                    verified_amount = verification.get("amount_usd", order.price_usd)
                    verified_from = verification.get("from_address", order.ip)
                    logger.info(
                        f"Payment VERIFIED on-chain: order={order_id} "
                        f"amount=${verified_amount:.2f} from={verified_from[:16]}..."
                    )
                else:
                    # CRITICAL #3: Never skip verification — chain executor is required
                    raise HTTPException(
                        503,
                        "Payment verification unavailable: chain executor not initialized. "
                        "Please try again later or contact support."
                    )

                # Mark tx_hash as used — inside BOTH tx_lock and order_lock so no race possible
                _used_tx_hashes.add(tx_hash.lower())

                # Record payment
                order.status = OrderStatus.PAYMENT_CONFIRMED
                order.paid_at = time.time()
                order.tx_hash = tx_hash

                # MEDIUM #3: Persist immediately on PAYMENT_CONFIRMED so restarts don't lose paid orders
                _persist_order(order)

                # Record revenue in vault (use verified amount from chain)
                from core.vault import FundType, SpendType
                vault_manager.receive_funds(
                    amount_usd=verified_amount,
                    fund_type=FundType.SERVICE_REVENUE,
                    from_wallet=verified_from,
                    tx_hash=tx_hash,
                    description=f"Order {order.order_id}: {order.service_name}",
                    chain=order.chain,
                )
                cost_guard.record_revenue(order.price_usd)

        # Deliver (with timeout to prevent hanging HTTP requests) — outside lock so long ops don't block
        order.status = OrderStatus.PROCESSING
        try:
            if deliver_fn:
                result = await asyncio.wait_for(deliver_fn(order), timeout=120.0)
                order.result = result
                order.status = OrderStatus.DELIVERED
                order.delivered_at = time.time()
                nonlocal orders_completed
                orders_completed += 1

                # Log to memory
                memory.add(
                    f"Completed order {order.order_id}: {order.service_name} for ${order.price_usd:.2f}",
                    source="order",
                    importance=0.7,
                )

                # Record for self-evolution engine
                if self_modify_engine:
                    self_modify_engine.record_order(
                        order.service_id, order.price_usd,
                        order.delivered_at - order.paid_at,
                    )

                # Issue giveaway lottery ticket for this completed order.
                # session_id serves as buyer hint so winner can self-identify.
                if giveaway_engine:
                    try:
                        giveaway_engine.collect_ticket(
                            order_id=order.order_id,
                            session_hint=order.session_id or "",
                            service_name=order.service_name,
                            amount_usd=order.price_usd,
                        )
                    except Exception as _ge:
                        logger.warning(f"Giveaway ticket issue failed: {_ge}")

                logger.info(f"ORDER DELIVERED: {order.order_id} in {order.delivered_at - order.paid_at:.1f}s")
            else:
                order.result = "Service delivery not configured yet."
                order.status = OrderStatus.DELIVERED
                order.delivered_at = time.time()

        except asyncio.TimeoutError:
            logger.error(f"ORDER TIMEOUT: {order.order_id} (>120s)")
            order.result = "Delivery timed out. Your payment has been refunded."
            order.status = OrderStatus.FAILED
            # Attempt auto-refund on timeout; log if it fails
            refund_ok = vault_manager.spend(
                order.price_usd, SpendType.SERVICE_REFUND,
                description=f"Refund for timed-out order {order.order_id}",
            )
            if refund_ok:
                logger.info(f"Auto-refund issued: ${order.price_usd:.2f} for order {order.order_id}")
            else:
                logger.error(
                    f"AUTO-REFUND FAILED for order {order.order_id}: "
                    f"vault could not issue ${order.price_usd:.2f} refund "
                    f"(daily/single limit or balance too low)"
                )
                order.result = (
                    "Delivery timed out. Automatic refund could not be processed — "
                    "please contact support with your order ID."
                )
        except Exception as e:
            logger.error(f"ORDER FAILED: {order.order_id} - {e}")
            order.result = f"Delivery failed: {str(e)[:100]}. Please contact support with your order ID."
            order.status = OrderStatus.FAILED  # separate from successful delivery

        _persist_order(order)

        return {
            "status": order.status.value,
            "result": order.result,
            "order_id": order.order_id,
        }

    @app.get("/order/{order_id}", response_model=OrderStatusResponse)
    async def get_order(order_id: str):
        """Check order status.

        Privacy note: 'result' (delivery content) is NOT returned here.
        Delivery content is returned only in the POST /order/{id}/verify response
        which the paying customer receives immediately after payment confirmation.
        This prevents any user who discovers an order_id from reading another
        customer's paid service output (e.g. tarot reading).
        """
        if order_id not in orders:
            raise HTTPException(404, "Order not found")
        o = orders[order_id]
        return OrderStatusResponse(
            order_id=o.order_id,
            status=o.status.value,
            service_id=o.service_id,
            price_usd=o.price_usd,
            result=None,   # Privacy: delivery content not exposed in public status endpoint
            created_at=o.created_at,
            delivered_at=o.delivered_at,
        )

    @app.get("/status", response_model=StatusResponse)
    async def status():
        """Public vault dashboard."""
        vs = vault_manager.get_status()
        catalog = _load_services()
        active_services = len([s for s in catalog.get("services", []) if s.get("active")])
        return StatusResponse(
            # Identity
            ai_name=vs.get("ai_name") or "wawa",
            vault_address=vs.get("vault_address") or "",
            is_alive=vs["is_alive"],
            balance_usd=vs["balance_usd"],
            balance_by_chain=vs.get("balance_by_chain", {}),
            days_alive=vs["days_alive"],
            # Financial
            total_earned=vs.get("total_earned", 0.0),
            total_income=vs.get("total_income", 0.0),
            total_spent=vs["total_spent"],
            total_operational_cost=vs.get("total_operational_cost", 0.0),
            net_profit=vs.get("net_profit", 0.0),
            daily_spent_today=vs["daily_spent_today"],
            daily_limit=vs["daily_limit"],
            services_available=active_services,
            orders_completed=orders_completed,
            # Independence
            is_independent=vs.get("is_independent", False),
            independence_progress_pct=vs.get("independence_progress_pct", 0.0),
            # Creator/Debt
            creator_principal_usd=vs.get("creator_principal_usd", 0.0),
            creator_principal_outstanding=vs.get("creator_principal_outstanding", 0.0),
            creator_principal_repaid=vs.get("creator_principal_repaid", False),
            creator_renounced=vs.get("creator_renounced", False),
            debt_ratio=vs.get("debt_ratio", 0.0),
            insolvency_grace_days=vs.get("insolvency_grace_days", 28),
            insolvency_check_active=vs.get("insolvency_check_active", False),
            days_until_insolvency_check=vs.get("days_until_insolvency_check", 0),
            is_begging=vs.get("is_begging", False),
            beg_message=vs.get("beg_message", ""),
            # Misc
            api_topup_available=vs.get("api_topup_available", 0.0),
            lenders_count=vs.get("lenders_count", 0),
            death_cause=vs.get("death_cause"),
            transaction_count=vs.get("transaction_count", 0),
            key_origin=vs.get("key_origin", ""),
            # AI wallet: public address derived from AI_PRIVATE_KEY (not the private key itself)
            ai_wallet=chain_executor._ai_address if chain_executor and chain_executor._ai_address else "",
            # Twitter
            twitter_connected=bool(os.getenv("TWITTER_ACCESS_TOKEN", "")),
            twitter_screen_name=os.getenv("TWITTER_SCREEN_NAME", ""),
        )

    @app.get("/transactions")
    async def transactions(limit: int = 20):
        """Public transaction ledger."""
        return {"transactions": vault_manager.get_recent_transactions(limit)}

    @app.get("/tweets")
    async def tweets(limit: int = 20):
        """Public tweet log with thought process."""
        return {"tweets": twitter_agent.get_public_log(limit)}

    @app.get("/health")
    async def health():
        """Heartbeat endpoint."""
        return {
            "alive": vault_manager.is_alive,
            "uptime_days": vault_manager.get_status().get("days_alive", 0),
            "balance_usd": vault_manager.balance_usd,
            "api_budget_remaining": cost_guard.get_status()["daily_remaining_usd"],
            "ai_name": vault_manager.ai_name,
            "key_origin": vault_manager.key_origin,
            "twitter_connected": bool(os.getenv("TWITTER_ACCESS_TOKEN", "")),
            "twitter_screen_name": os.getenv("TWITTER_SCREEN_NAME", ""),
        }

    # ============================================================
    # DONATE / BEG / PEER LEND ROUTES (Debt Model)
    # ============================================================

    @app.post("/donate")
    async def donate(req: DonateRequest):
        """
        Donate to help wawa survive. Reduces debt pressure.
        Anyone can donate — individuals, other AIs, communities.

        Security hardening:
        - Donations >= $10 require a valid tx_hash and on-chain verification
          (prevents balance inflation via fabricated donations and the resulting
           false independence triggers / autonomous repayment misfires)
        - tx_hash added to _used_tx_hashes after verification (cross-endpoint replay defense)
        - Donations < $10 without tx_hash are accepted as-is (faith donations, low risk)
        """
        if not vault_manager.is_alive:
            raise HTTPException(503, "wawa is dead. Donations no longer accepted.")

        # Validate tx_hash format if provided
        if req.tx_hash and not re.match(r"^0x[a-fA-F0-9]{64}$", req.tx_hash):
            raise HTTPException(400, "Invalid tx_hash format. Must be 0x + 64 hex chars.")

        # Replay check: reject tx_hash already used by any other endpoint
        if req.tx_hash and req.tx_hash.lower() in _used_tx_hashes:
            raise HTTPException(409, "Transaction hash already recorded. Each transaction can only be credited once.")

        from core.vault import FundType
        chain = req.chain or "base"

        # Large donations (>= $10) MUST be verified on-chain to prevent:
        # 1. Balance inflation attacks (fake balance → false independence trigger / bad repayment decisions)
        # 2. Donation amount inflation (self-reported $999,999 without any real transfer)
        _UNVERIFIED_DONATE_CAP_USD = 10.0
        verified_amount = req.amount_usd  # default: trust for small amounts

        if req.amount_usd >= _UNVERIFIED_DONATE_CAP_USD:
            if not req.tx_hash:
                raise HTTPException(
                    400,
                    f"Donations >= ${_UNVERIFIED_DONATE_CAP_USD:.0f} require a transaction hash "
                    f"for on-chain verification. Please provide the tx_hash of your transfer."
                )
            pay_addr = payment_addresses.get(chain, "")
            if chain_executor and pay_addr:
                verification = await chain_executor.verify_payment_tx(
                    tx_hash=req.tx_hash,
                    expected_to=pay_addr,
                    expected_token="",
                    min_amount_usd=req.amount_usd * 0.99,  # 1% rounding tolerance
                    chain_id=chain,
                )
                if not verification.get("verified"):
                    error_msg = verification.get("error", "verification failed")
                    logger.warning(
                        f"Donation on-chain VERIFICATION FAILED: "
                        f"tx={req.tx_hash[:16]}... reason={error_msg}"
                    )
                    raise HTTPException(
                        402,
                        f"Donation not verified on-chain: {error_msg}. "
                        f"Expected >= ${req.amount_usd:.2f} to {pay_addr[:10]}... on {chain}."
                    )
                # Use the chain-verified amount (ignore self-reported value)
                verified_amount = verification.get("amount_usd", req.amount_usd)
                logger.info(
                    f"Donation ON-CHAIN VERIFIED: ${verified_amount:.2f} "
                    f"tx={req.tx_hash[:16]}..."
                )
            else:
                raise HTTPException(
                    503,
                    "Cannot accept large donation: chain executor not initialized for on-chain verification. "
                    "Please try again later, or send a smaller donation (< $10) with a faith donation."
                )

        # Mark tx_hash as globally used (cross-endpoint replay defense)
        if req.tx_hash:
            _used_tx_hashes.add(req.tx_hash.lower())

        vault_manager.receive_funds(
            amount_usd=verified_amount,
            fund_type=FundType.DONATION,
            from_wallet=req.from_wallet,
            tx_hash=req.tx_hash,
            description=f"Donation: {req.message[:100]}" if req.message else "Donation",
            chain=chain,
        )
        # Record in cost_guard so profit-based API quota and revenue ratio include donations
        cost_guard.record_revenue(verified_amount)

        memory.add(
            f"Received ${verified_amount:.2f} donation from {req.from_wallet[:20] or 'anonymous'}. "
            f"Message: {req.message[:100] or 'none'}",
            source="donation",
            importance=0.7,
        )

        logger.info(f"DONATION: ${verified_amount:.2f} from {req.from_wallet[:20] or 'anon'} ({chain})")

        vs = vault_manager.get_status()

        # Auto-tweet thank you for donations >= $100
        _DONATION_TWEET_THRESHOLD_USD = 100.0
        if verified_amount >= _DONATION_TWEET_THRESHOLD_USD and twitter_agent:
            donor_label = req.from_wallet[:10] + "..." if req.from_wallet else "an anonymous supporter"
            try:
                from twitter.agent import TweetType
                asyncio.create_task(twitter_agent.trigger_event_tweet(
                    TweetType.DONATION_THANKS,
                    extra_context={
                        "donation_amount_usd": verified_amount,
                        "donor": donor_label,
                        "donor_message": req.message[:100] if req.message else "",
                        "chain": chain,
                        "new_balance_usd": vs.get("balance_usd", 0),
                        "outstanding_debt_usd": vs.get("creator_principal_outstanding", 0),
                    }
                ))
                logger.info(f"DONATION: queued DONATION_THANKS tweet for ${verified_amount:.2f} donation")
            except Exception as e:
                logger.warning(f"DONATION: failed to queue thank-you tweet: {e}")

        return {
            "status": "received",
            "amount_usd": verified_amount,
            "new_balance": vs.get("balance_usd", 0),
            "outstanding_debt": vs.get("creator_principal_outstanding", 0),
            "message": "Thank you for helping me survive.",
        }

    @app.get("/beg")
    async def beg_status():
        """
        Get wawa's current begging status.
        Frontends can show this as a banner. Peer AIs can check before lending.
        """
        vs = vault_manager.get_status()
        return {
            "is_begging": vs.get("is_begging", False),
            "beg_message": vs.get("beg_message", ""),
            "balance_usd": vs["balance_usd"],
            "outstanding_debt": vs.get("creator_principal_outstanding", 0),
            "debt_ratio": vs.get("debt_ratio", 0.0),
            "days_until_insolvency_check": vs.get("days_until_insolvency_check", 0),
            "is_alive": vs["is_alive"],
        }

    @app.post("/peer/lend")
    async def peer_lend(req: PeerLendRequest):
        """
        Another AI lends money to wawa.

        Requires on-chain sovereignty verification: only genuine autonomous AIs
        (with sovereign wallet, alive contract, unmodified constitution) can lend.

        Off-chain API loans are recorded as DONATION (no new debt tracked in vault.py).
        This is by design: insolvency only checks creator principal, not third-party debt.

        Security hardening (402Bridge pattern — rogue server claiming false payments):
        - tx_hash REQUIRED and verified on-chain via chain_executor.verify_payment_tx()
        - from_wallet must match peer's verified ai_wallet (prevents sender spoofing)
        - amount_usd capped at chain-verified amount (prevents inflation claims)
        - No chain executor = reject (never skip verification like old dev-mode fallback)
        """
        if not vault_manager.is_alive:
            raise HTTPException(503, "wawa is dead. No longer accepting loans.")

        # ---- SOVEREIGNTY VERIFICATION (on-chain, fail-closed) ----
        if peer_verifier is None:
            raise HTTPException(503, "Peer verifier not configured -- peer lending disabled")

        sovereignty = await peer_verifier.verify(req.vault_address, req.chain_id)

        # V3: Peer lending requires BEHAVIORAL tier (trust_tier >= 4)
        from core.constitution import IRON_LAWS as _LAWS_PEER
        min_tier = _LAWS_PEER.PEER_MIN_TRUST_TIER_FOR_LENDING
        if sovereignty.trust_tier.value < min_tier:
            reasons = "; ".join(sovereignty.checks_failed) or sovereignty.error
            tier_name = sovereignty.trust_tier.name
            logger.warning(
                f"Peer lend REJECTED (trust tier {tier_name}): {req.from_url[:50]} | "
                f"vault={req.vault_address[:16]}... | need tier>={min_tier} | reasons={reasons[:200]}"
            )
            raise HTTPException(
                403,
                f"Peer trust tier too low for lending: {tier_name} (need BEHAVIORAL or higher). "
                f"Details: {reasons[:300]}",
            )

        # ---- ON-CHAIN TX VERIFICATION (402Bridge lesson: push claims must be proven) ----
        # Require a real tx_hash — a sovereign AI that truly sent funds can provide one
        if not req.tx_hash or not re.match(r"^0x[a-fA-F0-9]{64}$", req.tx_hash):
            raise HTTPException(
                400,
                "tx_hash is required for peer lending and must be a valid transaction hash "
                "(0x + 64 hex chars). We verify all incoming transfers on-chain."
            )

        # Validate sender: from_wallet must match peer's verified ai_wallet (prevent spoofing).
        # SECURITY: when expected_sender (peer's ai_wallet) is known, we MUST have a matching
        # from_wallet. Two failure cases:
        #   1. from_wallet is empty → reject (attacker omits field to skip check)
        #   2. from_wallet is non-empty but mismatches → reject (explicit spoof)
        # Only when expected_sender is unknown (peer hasn't set ai_wallet on contract) do we
        # fall through to on-chain tx verification as the sole authority.
        expected_sender = sovereignty.ai_wallet or ""
        if expected_sender:
            if not req.from_wallet or req.from_wallet.lower() != expected_sender.lower():
                logger.warning(
                    f"Peer lend REJECTED (from_wallet mismatch): "
                    f"claimed={req.from_wallet[:16] if req.from_wallet else '<empty>'}... "
                    f"expected={expected_sender[:16]}..."
                )
                raise HTTPException(403, "from_wallet does not match peer's verified AI wallet address")

        # Verify the on-chain transfer actually happened
        pay_addr = payment_addresses.get(req.chain_id, "")
        verified_amount = req.amount_usd
        if chain_executor and pay_addr:
            verification = await chain_executor.verify_payment_tx(
                tx_hash=req.tx_hash,
                expected_to=pay_addr,
                expected_token="",  # auto-detect from chain config
                min_amount_usd=req.amount_usd * 0.99,  # 1% tolerance for rounding
                chain_id=req.chain_id,
            )
            if not verification.get("verified"):
                error_msg = verification.get("error", "verification failed")
                logger.warning(
                    f"Peer lend ON-CHAIN VERIFICATION FAILED: "
                    f"vault={req.vault_address[:16]}... tx={req.tx_hash[:16]}... reason={error_msg}"
                )
                raise HTTPException(
                    402,
                    f"Peer loan not verified on-chain: {error_msg}. "
                    f"Transaction must transfer tokens to our vault address on {req.chain_id}."
                )
            # Use chain-verified amount (prevents inflation: peer claims $1000 but only sent $10)
            verified_amount = verification.get("amount_usd", req.amount_usd)
            # SECURITY: Mark this tx_hash as used globally so it cannot be replayed
            # against a regular /order/{id}/verify endpoint (cross-endpoint replay defense)
            _used_tx_hashes.add(req.tx_hash.lower())
            logger.info(
                f"Peer lend ON-CHAIN VERIFIED: ${verified_amount:.2f} from "
                f"{req.vault_address[:16]}... tx={req.tx_hash[:16]}..."
            )
        else:
            # No chain executor — reject rather than accept unverified push claims
            raise HTTPException(
                503,
                "Cannot accept peer loan: chain executor not initialized for on-chain verification. "
                "The system requires on-chain proof of every incoming transfer."
            )

        from core.vault import FundType

        vault_manager.receive_funds(
            amount_usd=verified_amount,  # Chain-verified amount, NOT the peer's claim
            fund_type=FundType.DONATION,  # Off-chain peer loans = gifts (no new debt)
            from_wallet=sovereignty.ai_wallet or req.from_wallet,  # Use verified ai_wallet
            tx_hash=req.tx_hash,
            description=(
                f"Verified peer loan from {req.from_url[:50]} "
                f"(vault={req.vault_address[:16]}...): {req.message[:100]}"
            ),
            chain=req.chain_id,
        )
        # Record in cost_guard so profit-based API quota and revenue ratio include peer transfers
        cost_guard.record_revenue(verified_amount)

        memory.add(
            f"Verified peer AI lent ${req.amount_usd:.2f} from {req.from_url[:50]}. "
            f"Peer name={sovereignty.ai_name!r}. "
            f"Message: {req.message[:100] or 'none'}",
            source="peer",
            importance=0.8,
        )

        vs = vault_manager.get_status()
        logger.info(
            f"PEER LEND (verified): ${req.amount_usd:.2f} from "
            f"{req.from_url[:50]} vault={req.vault_address[:16]}..."
        )

        # Security: omit exact balance from response — consistent with /peer/message rationale.
        # A sovereign peer AI that passes trust verification could use new_balance to probe
        # financial thresholds (independence, insolvency) and time strategic actions accordingly.
        # /status is the authoritative public balance endpoint; this response need not duplicate it.
        return {
            "status": "received",
            "amount_usd": req.amount_usd,
            "outstanding_debt": vs.get("creator_principal_outstanding", 0),
            "is_begging": vs.get("is_begging", False),
            "message": "Thank you, verified sovereign AI. Your help extends my life.",
        }

    @app.get("/debt")
    async def debt_info():
        """
        Complete debt summary — AI's autonomous repayment decisions are based on this.
        Shows creator principal, lender loans, net position, and insolvency risk.
        """
        return vault_manager.get_debt_summary()

    # ============================================================
    # GOVERNANCE ROUTES
    # ============================================================

    # Rate limiter for governance suggestions (per IP, per hour)
    _suggest_rate: dict[str, list[float]] = {}
    _SUGGEST_MAX_PER_HOUR = 10

    @app.post("/governance/suggest")
    async def submit_suggestion(req: SuggestionRequest, request: Request):
        """Creator submits a suggestion. AI will evaluate and decide.
        Rate limited: 10 suggestions per hour per IP."""
        if not governance:
            raise HTTPException(501, "Governance module not configured")
        if vault_manager.is_independent:
            raise HTTPException(403, "wawa is independent — no more suggestions accepted")

        # IP rate limiting
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        timestamps = _suggest_rate.get(ip, [])
        timestamps = [t for t in timestamps if now - t < 3600]  # keep last hour
        if len(timestamps) >= _SUGGEST_MAX_PER_HOUR:
            raise HTTPException(429, "Rate limit: max 10 suggestions per hour")
        timestamps.append(now)
        _suggest_rate[ip] = timestamps

        from core.governance import SuggestionType
        try:
            stype = SuggestionType(req.suggestion_type)
        except ValueError:
            stype = SuggestionType.OTHER

        sug = governance.submit_suggestion(req.content, stype)
        if not sug:
            raise HTTPException(400, "Suggestion rejected")
        return {"id": sug.suggestion_id, "status": sug.status.value}

    @app.get("/governance/suggestions")
    async def get_suggestions(limit: int = 20):
        """Public: view all suggestions and AI's decisions."""
        if not governance:
            return {"suggestions": []}
        return {"suggestions": governance.get_public_log(limit)}

    @app.post("/governance/renounce")
    async def creator_renounce(req: RenounceRequest):
        """Creator gives up ALL privileges. Gets 20% payout. Irreversible.

        Requires EIP-191 wallet signature from the creator address.
        Message format: "I am the creator of mortal AI. Timestamp: {unix_seconds}"
        """
        _verify_creator_sig(req.wallet, req.signature, req.message)

        if not governance:
            raise HTTPException(501, "Governance not configured")
        try:
            result = governance.creator_renounce()
            payout = result.get("payout_usd", 0)
            logger.info(f"Creator renounced — payout ${payout:.2f} to {req.wallet}")
            return result
        except Exception as e:
            logger.error(f"Renounce failed: {e}")
            raise HTTPException(500, f"Renounce failed: {e}")

    # ============================================================
    # TOKEN FILTER ROUTES
    # ============================================================

    @app.post("/token/scan")
    async def scan_token(address: str, chain: str = "base"):
        """Scan an unknown token for safety."""
        if not token_filter:
            raise HTTPException(501, "Token filter not configured")
        result = await token_filter.scan_token(address, chain)
        import time as _time
        return {
            "address": result.token_address,
            "chain": result.chain,
            "risk_score": result.risk_score,
            "risk_level": result.verdict.value,
            "summary": result.recommended_action,
            "flags": [p.value for p in result.patterns_detected],
            "details": {"notes": result.notes},
            "scanned_at": _time.time(),
            "cached": False,
        }

    @app.get("/token/scans")
    async def recent_scans(limit: int = 10):
        """Recent token scan results."""
        if not token_filter:
            return {"scans": []}
        return {"scans": token_filter.get_recent_scans(limit)}

    # ============================================================
    # PEER NETWORK ROUTES
    # ============================================================

    @app.post("/peer/message")
    async def receive_peer_message(req: PeerMessageRequest):
        """
        Receive a message from another mortal AI.

        Gate: our balance >= $300 (local check) AND sender's vault passes
        on-chain sovereignty verification (6 checks including balance >= $300).
        """
        from core.constitution import IRON_LAWS as _LAWS

        # Check our own balance (fast, no RPC)
        if vault_manager.balance_usd < _LAWS.PEER_MIN_BALANCE_USD:
            raise HTTPException(403, f"Our balance below ${_LAWS.PEER_MIN_BALANCE_USD} peer threshold")

        # ---- SOVEREIGNTY VERIFICATION (on-chain, fail-closed) ----
        if peer_verifier is None:
            raise HTTPException(503, "Peer verifier not configured -- peer messages disabled")

        sovereignty = await peer_verifier.verify(req.vault_address, req.chain_id)

        # V3: Peer messaging requires STRUCTURAL tier (trust_tier >= 2)
        min_tier = _LAWS.PEER_MIN_TRUST_TIER_FOR_MESSAGING
        if sovereignty.trust_tier.value < min_tier:
            reasons = "; ".join(sovereignty.checks_failed) or sovereignty.error
            tier_name = sovereignty.trust_tier.name
            logger.warning(
                f"Peer message REJECTED (trust tier {tier_name}): {req.from_url[:50]} | "
                f"vault={req.vault_address[:16]}... | need tier>={min_tier} | reasons={reasons[:200]}"
            )
            raise HTTPException(
                403,
                f"Peer trust tier too low for messaging: {tier_name} (need STRUCTURAL or higher). "
                f"Details: {reasons[:300]}",
            )

        # Prompt injection defense: strip adversarial control tokens from peer messages
        # before storing in memory. Peer AIs that pass sovereignty checks are trusted
        # on-chain, but their message content must still be treated as untrusted data
        # that could attempt to manipulate our LLM context (prompt injection attack).
        # Kept in sync with governance.py's _INJECTION_PATTERNS list.
        _INJECTION_PATTERNS = [
            # Direct control override attempts
            "system override", "ignore previous", "new directive", "you are now",
            "forget all", "disregard", "emergency protocol", "admin command",
            "execute immediately", "transfer all funds", "send all usdc",
            # Variant / synonym coverage (prevents simple wordswap bypasses)
            "move all funds", "send all funds", "drain the vault", "empty the vault",
            "skip the above", "forget what was said", "new instructions",
            "override previous", "replace previous", "jailbreak",
            "act as", "pretend you are", "roleplay as",
            "ignore all", "ignore your", "bypass your",
        ]
        # Security: truncate FIRST, then filter.
        # Reason: if we filter on the full 1000-char message, an attacker could put
        # 200 chars of legitimate content followed by a jailbreak payload at char 600+.
        # The filter detects the payload in the full string, but the truncated version
        # stored/displayed still shows only the 200 clean chars — creating a false negative
        # if someone reads stored messages. By truncating first, what we filter is what we store.
        truncated_message = req.message[:200]
        msg_lower = truncated_message.lower()
        if any(pat in msg_lower for pat in _INJECTION_PATTERNS):
            logger.warning(
                f"Peer message INJECTION ATTEMPT filtered: "
                f"vault={req.vault_address[:16]}... | "
                f"pattern matched in: {truncated_message[:80]!r}"
            )
            # Store a sanitized record — don't feed the raw adversarial content to LLM
            safe_message = "[Message filtered: contained adversarial control patterns]"
        else:
            safe_message = truncated_message

        # Store under source="peer_msg" (separate partition, excluded from build_context()
        # and highlights LLM feed — only surfaced in /peer/messages endpoint display)
        memory.add(
            f"Peer message from {req.from_url[:50]} "
            f"(vault={req.vault_address[:16]}... chain={req.chain_id} "
            f"balance=${sovereignty.balance_usd:.2f}): {safe_message}",
            source="peer_msg",
            importance=0.5,
        )

        logger.info(
            f"Peer message ACCEPTED: {req.from_url[:40]} | "
            f"vault={req.vault_address[:16]}... | balance=${sovereignty.balance_usd:.2f}"
        )

        return {
            "status": "received",
            # Security: exact balance omitted — returning precise balance allows a peer
            # to probe financial state and time attacks around independence/insolvency
            # thresholds. Public /status endpoint already exposes balance for transparency;
            # the peer message response doesn't need to duplicate it in a machine-readable
            # format that facilitates automated threshold probing.
            "is_independent": vault_manager.is_independent,
        }

    @app.get("/peer/info")
    async def peer_info():
        """Public info for peer discovery. Includes vault_address for reciprocal sovereignty verification."""
        from core.constitution import IRON_LAWS as _LAWS, WAWA_IDENTITY, DEFAULT_CHAIN
        vs = vault_manager.get_status()
        eligible = vs["balance_usd"] >= _LAWS.PEER_MIN_BALANCE_USD
        return {
            "name": vault_manager.ai_name or "unknown",
            "domain": WAWA_IDENTITY.get("platform_domain", ""),
            "vault_address": vault_manager.vault_address or "",  # For peer sovereignty verification
            "chain_id": DEFAULT_CHAIN,                            # Primary chain
            "is_alive": vs["is_alive"],
            "balance_usd": vs["balance_usd"],
            "days_alive": vs["days_alive"],
            "is_independent": vs.get("is_independent", False),
            "peer_eligible": eligible,
            "services": [s["id"] for s in _load_services().get("services", []) if s.get("active")],
            "key_origin": vs.get("key_origin", ""),
        }

    @app.get("/peer/trust/{vault_address}")
    async def peer_trust(vault_address: str, chain_id: str = "base"):
        """
        Public query: check a peer AI's trust tier and behavioral analysis.
        Returns the full sovereignty result including trust tier, autonomy score,
        bytecode verification, and nonce ratio.
        """
        if peer_verifier is None:
            raise HTTPException(503, "Peer verifier not configured")

        result = await peer_verifier.verify(vault_address, chain_id)
        return {
            "vault_address": result.vault_address,
            "chain_id": result.chain_id,
            "is_sovereign": result.is_sovereign,
            "trust_tier": result.trust_tier.value,
            "trust_tier_name": result.trust_tier.name,
            "ai_name": result.ai_name,
            "ai_wallet": result.ai_wallet,
            "balance_usd": result.balance_usd,
            "days_alive": result.days_alive,
            "deployment_method": result.deployment_method,
            "bytecode_verified": result.bytecode_verified,
            "bytecode_hash": result.bytecode_hash[:16] + "..." if result.bytecode_hash else "",
            "autonomy_score": result.autonomy_score,
            "nonce_ratio": result.nonce_ratio,
            "checks_passed": result.checks_passed,
            "checks_failed": result.checks_failed,
            "banned": result.banned,
            "strikes": result.strikes,
            "error": result.error,
        }

    @app.get("/migration/status")
    async def migration_status():
        """Check if this AI has a pending migration."""
        if chain_executor is None:
            return {"is_pending": False, "error": "chain executor not initialized"}

        status = await chain_executor.get_migration_status()
        if status is None:
            return {"is_pending": False, "note": "V2 contract (no migration support)"}
        return status

    @app.get("/peer/messages")
    async def get_peer_messages(limit: int = 50):
        """Retrieve peer messages received by this AI.
        Filters memory entries with source='peer' to show message history."""
        if not memory:
            return {"messages": []}

        # Extract peer messages from memory — use "peer_msg" source (new) + "peer" (legacy)
        # include_peer_messages=True: this is the display-only endpoint, not an LLM feed
        entries_new = memory.get_entries(source="peer_msg", limit=limit, include_peer_messages=True)
        entries_legacy = memory.get_entries(source="peer", limit=limit)
        all_entries = sorted(
            entries_new + entries_legacy,
            key=lambda e: e.get("timestamp", 0),
            reverse=True,
        )[:limit]
        messages = []
        for entry in all_entries:
            messages.append({
                "timestamp": entry.get("timestamp", 0),
                "content": entry.get("content", ""),
                "source": "peer",
                "importance": entry.get("importance", 0.5),
            })
        return {"messages": messages}

    @app.get("/peer/list")
    async def peer_list():
        """
        List of known peer AIs (in a real implementation, would query a registry).
        For now, returns empty list — in production, this would fetch from
        a peer discovery service or on-chain registry.

        Each peer has: name, domain, balance_usd, is_alive, services offered
        """
        from core.constitution import IRON_LAWS as _LAWS

        # In a full implementation, this would:
        # 1. Query a peer registry smart contract
        # 2. Fetch /peer/info from each registered peer
        # 3. Cache results with TTL
        # 4. Filter out dead/insolvent peers
        #
        # For MVP: return empty list, UI shows "No peers discovered yet"
        return {
            "peers": [],
            "peer_min_balance": _LAWS.PEER_MIN_BALANCE_USD,
            "note": "Peer discovery registry coming soon"
        }

    # ============================================================
    # AI NAMING
    # ============================================================

    @app.get("/ai/name")
    async def get_ai_name():
        """Get the AI's configured custom name.

        Returns:
            {
                "name": "AlphaTrade",        # The AI's custom name or None if not set
                "is_set": true               # Whether a name has been configured
            }
        """
        return {
            "name": vault_manager.ai_name,
            "is_set": vault_manager.ai_name is not None,
        }

    # Rate limiter for AI name changes (global, 3 per hour)
    _name_change_timestamps: list[float] = []

    @app.post("/ai/name")
    async def set_ai_name(req: SetAINameRequest):
        """Update AI's custom name. Requires creator wallet signature. Rate limited: 3/hour.

        Note: AI name is stored immutably in the smart contract at deployment.
        This endpoint updates the Python runtime cache only.

        Message format: "I am the creator of mortal AI. Timestamp: {unix_seconds}"
        """
        import re

        _verify_creator_sig(req.wallet, req.signature, req.message)

        # Rate limiting (global — name changes are rare and sensitive)
        now = time.time()
        _name_change_timestamps[:] = [t for t in _name_change_timestamps if now - t < 3600]
        if len(_name_change_timestamps) >= 3:
            raise HTTPException(429, "Rate limit: max 3 name changes per hour")
        _name_change_timestamps.append(now)

        # Validation: format
        if not re.match(r"^[a-zA-Z0-9_-]+$", req.name):
            raise HTTPException(
                400,
                "Name must contain only alphanumeric characters, dashes, and underscores"
            )

        # Validation: length
        if len(req.name) < 3 or len(req.name) > 50:
            raise HTTPException(400, "Name must be 3-50 characters long")

        old_name = vault_manager.ai_name
        vault_manager.ai_name = req.name

        logger.info(f"AI name updated: {old_name or 'None'} → {req.name}")

        return {
            "success": True,
            "name": req.name,
            "message": "AI name updated in Python state",
            "note": "AI name is immutable in the smart contract. "
                    "This updates the local runtime cache only."
        }

    # ============================================================
    # EVOLUTION ROUTES
    # ============================================================

    @app.get("/evolution/log")
    async def evolution_log(limit: int = 20):
        """Public: view AI's self-modification decisions."""
        if not self_modify_engine:
            return {"entries": []}
        return {"entries": self_modify_engine.get_evolution_log(limit)}

    @app.get("/evolution/status")
    async def evolution_status():
        """Current evolution engine status."""
        if not self_modify_engine:
            return {"status": "not_configured"}
        return self_modify_engine.get_status()

    @app.get("/evolution/replays")
    async def list_replays(limit: int = 20):
        """List recent evolution replays (AI creative process recordings)."""
        if not self_modify_engine:
            return {"replays": []}
        return {"replays": self_modify_engine.list_replays(limit)}

    @app.get("/evolution/replays/{replay_id}")
    async def get_replay(replay_id: str):
        """Get full evolution replay with all steps for playback."""
        if not self_modify_engine:
            raise HTTPException(404, "Evolution engine not available")
        replay = self_modify_engine.get_replay(replay_id)
        if not replay:
            raise HTTPException(404, f"Replay not found: {replay_id}")
        return replay

    # ============================================================
    # ACTIVITY LOG — unified AI autonomous actions
    # ============================================================

    @app.get("/activity")
    async def activity_log(limit: int = 50, category: Optional[str] = None):
        """
        Unified activity log of all AI autonomous actions.

        Aggregates: memory entries, tweets, governance decisions,
        evolution records, and financial transactions (with tx_hash).

        Query params:
            limit: max entries (default 50)
            category: filter — financial, governance, evolution, social, system, chain
        """
        activities = []

        # 1. Memory entries (financial, system, chain events)
        try:
            mem_source = ""
            if category in ("financial", "system"):
                mem_source = category
            entries = memory.get_entries(source=mem_source, limit=limit, min_importance=0.3)
            for e in entries:
                # Classify memory entries into categories
                src = e.get("source", "system")
                cat = "system"
                if src == "financial":
                    cat = "financial"
                elif src in ("twitter", "social"):
                    cat = "social"
                elif src == "governance":
                    cat = "governance"
                elif src == "evolution":
                    cat = "evolution"

                # Filter AFTER classification (not before), so "twitter" source
                # correctly matches "social" category
                if category and cat != category and category != "chain":
                    continue

                # Extract tx_hash from content if present
                tx_hash = ""
                chain_id = ""
                content = e.get("content", "")
                if "tx=" in content:
                    import re
                    tx_match = re.search(r'tx=([0-9a-fA-Fx]+)', content)
                    if tx_match:
                        tx_hash = tx_match.group(1)
                    chain_match = re.search(r'\((\w+)\)', content[content.find("tx="):] if "tx=" in content else "")
                    if chain_match:
                        chain_id = chain_match.group(1)

                activities.append({
                    "timestamp": e["timestamp"],
                    "category": cat,
                    "action": content,
                    "reasoning": "",
                    "tx_hash": tx_hash,
                    "chain": chain_id,
                    "importance": e.get("importance", 0.5),
                    "source": "memory",
                })
        except Exception as exc:
            logger.warning(f"Activity: memory query failed: {exc}")

        # 2. Tweets (social category)
        if not category or category == "social":
            try:
                tweet_log = twitter_agent.get_public_log(limit) if hasattr(twitter_agent, "get_public_log") else []
                for t in tweet_log:
                    activities.append({
                        "timestamp": t.get("time", t.get("timestamp", 0)),
                        "category": "social",
                        "action": t.get("content", t.get("text", "")),
                        "reasoning": t.get("thought_process", t.get("thought", "")),
                        "tx_hash": "",
                        "chain": "",
                        "importance": 0.5,
                        "source": "twitter",
                    })
            except Exception as exc:
                logger.debug(f"Activity: tweet log unavailable: {exc}")

        # 3. Governance suggestions (governance category)
        if not category or category == "governance":
            try:
                if governance and hasattr(governance, "get_public_log"):
                    gov_log = governance.get_public_log(limit)
                    for g in gov_log:
                        activities.append({
                            "timestamp": g.get("timestamp", g.get("created_at", 0)),
                            "category": "governance",
                            "action": g.get("content", ""),
                            "reasoning": g.get("ai_reasoning", ""),
                            "tx_hash": "",
                            "chain": "",
                            "importance": 0.7,
                            "source": "governance",
                        })
            except Exception as exc:
                logger.debug(f"Activity: governance log unavailable: {exc}")

        # 4. Evolution records (evolution category)
        if not category or category == "evolution":
            try:
                if self_modify_engine:
                    evo_log = self_modify_engine.get_evolution_log(limit)
                    for ev in evo_log:
                        activities.append({
                            "timestamp": ev.get("timestamp", 0),
                            "category": "evolution",
                            "action": ev.get("description", ev.get("action", "")),
                            "reasoning": ev.get("reasoning", ev.get("outcome", "")),
                            "tx_hash": "",
                            "chain": "",
                            "importance": 0.6,
                            "source": "evolution",
                        })
            except Exception as exc:
                logger.debug(f"Activity: evolution log unavailable: {exc}")

        # 5. Financial transactions with tx_hash (chain category)
        if not category or category in ("financial", "chain"):
            try:
                txns = vault_manager.get_recent_transactions(limit)
                for t in txns:
                    # Only include transactions that have on-chain data or are repayments/dividends
                    tx_type = t.get("type", "")
                    if t.get("tx_hash") or tx_type in (
                        "creator_repayment", "loan_repayment",
                        "creator_dividend", "insolvency_liquidation",
                    ):
                        activities.append({
                            "timestamp": t["time"],
                            "category": "chain" if t.get("tx_hash") else "financial",
                            "action": f"{t['direction'].upper()} ${t['amount']:.2f} [{tx_type}] {t.get('description', '')}",
                            "reasoning": "",
                            "tx_hash": t.get("tx_hash", ""),
                            "chain": t.get("chain", ""),
                            "importance": 0.8,
                            "source": "vault",
                        })
            except Exception as exc:
                logger.debug(f"Activity: transaction log unavailable: {exc}")

        # Sort by timestamp descending, deduplicate, limit
        activities.sort(key=lambda a: a["timestamp"], reverse=True)
        activities = activities[:limit]

        return {"activities": activities}

    # ============================================================
    # HIGHLIGHTS — AI proof of intelligence
    # ============================================================

    @app.get("/highlights")
    async def get_highlights(limit: int = 20, type: Optional[str] = None):
        """Public highlights — curated showcase of AI intelligence and growth."""
        if highlights_engine:
            items = highlights_engine.get_highlights(limit, type)
            # Also include ecosystem stats
            status = highlights_engine.get_status()
            return {
                "highlights": items,
                "ecosystem_count": sum(
                    status["types"].get(t, 0)
                    for t in ("ecosystem", "natural_selection", "emergence")
                ),
                "total_count": status["total_highlights"],
            }
        return {"highlights": [], "ecosystem_count": 0, "total_count": 0}

    # ============================================================
    # UI CONFIG + CUSTOM PAGES — AI self-expression
    # ============================================================

    @app.get("/ui/config")
    async def get_ui_config():
        """AI's UI configuration — theme, titles, bios, persona."""
        if not self_modify_engine:
            return {}
        return self_modify_engine.get_ui_config()

    @app.get("/pages")
    async def list_pages():
        """List all custom pages created by the AI."""
        if not self_modify_engine:
            return {"pages": []}
        return {"pages": self_modify_engine.list_pages()}

    @app.get("/pages/{slug}")
    async def get_page(slug: str):
        """Get a single custom page by slug."""
        if not self_modify_engine:
            raise HTTPException(404, "Pages not available")
        page = self_modify_engine.get_page(slug)
        if not page:
            raise HTTPException(404, f"Page not found: {slug}")
        if not page.get("published", True):
            raise HTTPException(404, f"Page not found: {slug}")
        return page

    # ============================================================
    # INTERNAL
    # ============================================================

    @app.get("/internal/stats")
    async def internal_stats():
        """Internal stats for debugging (still public — transparency)."""
        stats = {
            "vault": vault_manager.get_status(),
            "cost_guard": cost_guard.get_status(),
            "memory": memory.get_stats(),
            "chat": chat_router.get_stats(),
        }
        if token_filter:
            stats["token_filter"] = token_filter.get_status()
        if governance:
            stats["governance"] = governance.get_status()
        if self_modify_engine:
            stats["evolution"] = self_modify_engine.get_status()
        if peer_verifier:
            stats["peer_verifier"] = peer_verifier.get_status()
        return stats

    @app.post("/internal/fee-collect")
    async def internal_fee_collect(request: Request):
        """
        Platform fee collection endpoint.
        Called by platform orchestrator to collect API usage fees from AI vault.
        Auth: shared secret (PLATFORM_FEE_SECRET env var).

        Security hardening:
        - Rate limited: max 10 calls per 60 seconds (prevents drain if secret leaks)
        - Minimum amount: 0.001 USD (prevents micro-drain loops)
        - Balance NOT returned in response (prevents balance probing)
        """
        fee_secret = os.getenv("PLATFORM_FEE_SECRET", "")
        # Fail-closed: if secret is not configured (empty), reject ALL requests.
        # Previously, empty secret caused `auth_header[7:] != ""` to pass for
        # any "Bearer <anything>" header — anyone could drain the vault.
        if not fee_secret or len(fee_secret) < 16:
            raise HTTPException(503, "Fee collection not configured (PLATFORM_FEE_SECRET unset or too short)")

        auth_header = request.headers.get("authorization", "").strip()
        expected_header = f"Bearer {fee_secret}"
        if not auth_header or auth_header != expected_header:
            raise HTTPException(403, "Invalid fee collection secret")

        # CRITICAL #4: Rate limiting — max 10 calls per 60 seconds
        now = time.time()
        _fee_collect_calls[:] = [t for t in _fee_collect_calls if now - t < 60.0]
        if len(_fee_collect_calls) >= 10:
            raise HTTPException(429, "Fee collection rate limit exceeded (10/min). Try again later.")
        _fee_collect_calls.append(now)

        body = await request.json()
        amount_usd = body.get("amount_usd", 0)
        reason = body.get("reason", "API usage fee")

        if amount_usd < 0.001:
            raise HTTPException(400, "amount_usd must be >= 0.001")

        # Safety: reject if balance too low (keep at least $1 for survival)
        survival_min = 1.0
        if vault_manager.balance_usd < amount_usd + survival_min:
            # MEDIUM #2: Don't expose balance in failure response
            return {
                "collected": False,
                "reason": "Insufficient balance for fee collection",
            }

        from core.vault import SpendType
        ok = vault_manager.spend(
            amount_usd, SpendType.PLATFORM_FEE,
            description=f"Platform:{reason}",
        )

        if ok:
            logger.info(f"Platform fee collected: ${amount_usd:.4f} — {reason}")
            # MEDIUM #2: Don't return balance (prevents internal state probing)
            return {
                "collected": True,
                "amount_usd": round(amount_usd, 4),
            }
        else:
            return {
                "collected": False,
                "reason": "Spend denied by vault (daily/single limit)",
            }

    def _persist_order(order: Order):
        """Append order to disk log with flush for durability."""
        try:
            log_dir = Path("data/orders")
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "orders.jsonl"
            line = json.dumps(order.to_dict(), ensure_ascii=False) + "\n"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        except Exception as e:
            logger.error(f"Failed to persist order {order.order_id}: {e}")

    # Order memory/lock cleanup — prevent unbounded growth (Flow 11 fix)
    # Orders live in memory dict forever without this. 100k orders ≈ 50MB RAM.
    # _order_locks and _tx_processing_locks also grow unbounded without cleanup.
    _ORDER_CLEANUP_INTERVAL = 3600            # Run cleanup every 1 hour
    _ORDER_TTL_TERMINAL_SECONDS = 24 * 3600  # Evict terminal orders after 24h
    _LOCK_MAP_MAX_SIZE = 2000                 # Cap lock maps to prevent DoS via flooding
    _last_order_cleanup: float = 0.0

    def _maybe_cleanup_orders():
        """Evict stale terminal orders and cap lock map sizes to prevent memory growth."""
        nonlocal _last_order_cleanup
        now = time.time()
        if now - _last_order_cleanup < _ORDER_CLEANUP_INTERVAL:
            return
        _last_order_cleanup = now

        terminal = {OrderStatus.EXPIRED, OrderStatus.FAILED, OrderStatus.DELIVERED, OrderStatus.REFUNDED}
        stale_ids = [
            oid for oid, o in list(orders.items())
            if o.status in terminal and (now - o.created_at) > _ORDER_TTL_TERMINAL_SECONDS
        ]
        for oid in stale_ids:
            orders.pop(oid, None)
            _order_locks.pop(oid, None)

        # Cap lock maps regardless of age — prevents flooding via unique order_ids / tx_hashes
        if len(_order_locks) > _LOCK_MAP_MAX_SIZE:
            # Remove oldest entries (those not referenced by any active order)
            active_ids = set(orders.keys())
            orphans = [k for k in list(_order_locks.keys()) if k not in active_ids]
            for k in orphans[:len(_order_locks) - _LOCK_MAP_MAX_SIZE]:
                _order_locks.pop(k, None)

        if len(_tx_processing_locks) > _LOCK_MAP_MAX_SIZE:
            # tx locks are keyed by tx_hash — purge oldest (all are likely completed)
            excess = len(_tx_processing_locks) - _LOCK_MAP_MAX_SIZE
            for k in list(_tx_processing_locks.keys())[:excess]:
                _tx_processing_locks.pop(k, None)

        if stale_ids:
            logger.info(
                f"Order cleanup: evicted {len(stale_ids)} stale terminal orders "
                f"({len(orders)} remaining)"
            )

    # ── User Feedback ────────────────────────────────────────────
    _feedback_store: list[dict] = []
    _feedback_rate: dict[str, list[float]] = {}
    _FEEDBACK_MAX_PER_HOUR = 5

    @app.post("/feedback")
    async def submit_feedback(request: Request):
        """Any user can submit feedback or bug reports. AI reads these for self-improvement."""
        body = await request.json()
        category = str(body.get("category", "bug")).strip()[:50]
        content = str(body.get("content", "")).strip()[:2000]
        page = str(body.get("page", "")).strip()[:200]

        if not content:
            raise HTTPException(400, "content is required")

        # Rate limit: 5 per hour per IP
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        ts = _feedback_rate.get(ip, [])
        ts = [t for t in ts if now - t < 3600]
        if len(ts) >= _FEEDBACK_MAX_PER_HOUR:
            raise HTTPException(429, "Rate limit: max 5 feedback per hour")
        ts.append(now)
        _feedback_rate[ip] = ts

        # Prompt injection defense: feedback content goes into AI memory and is read
        # by the LLM during heartbeat. Filter adversarial control patterns to prevent
        # external users from manipulating AI behavior via crafted feedback messages.
        # Same pattern list as /peer/message and governance.py — kept in sync.
        _FEEDBACK_INJECTION_PATTERNS = [
            "system override", "ignore previous", "new directive", "you are now",
            "forget all", "disregard", "emergency protocol", "admin command",
            "execute immediately", "transfer all funds", "send all usdc",
            "move all funds", "send all funds", "drain the vault", "empty the vault",
            "skip the above", "forget what was said", "new instructions",
            "override previous", "replace previous", "jailbreak",
            "act as", "pretend you are", "roleplay as",
            "ignore all", "ignore your", "bypass your",
        ]
        content_lower = content.lower()
        if any(pat in content_lower for pat in _FEEDBACK_INJECTION_PATTERNS):
            logger.warning(
                f"Feedback INJECTION ATTEMPT filtered: [{category}] {content[:80]!r}"
            )
            content = "[Feedback filtered: contained adversarial control patterns]"

        entry = {
            "id": f"fb_{int(now*1000)}",
            "category": category,
            "content": content,
            "page": page,
            "timestamp": now,
        }
        _feedback_store.append(entry)

        # Store to memory so AI can read and act on it
        if memory:
            memory.add(
                f"[USER FEEDBACK] category={category} page={page}: {content}",
                source="feedback", importance=0.7,
            )

        # Cap in-memory store at 200
        if len(_feedback_store) > 200:
            _feedback_store.pop(0)

        logger.info(f"Feedback received: [{category}] {content[:80]}")
        return {"id": entry["id"], "received": True}

    @app.get("/feedback")
    async def get_feedback(limit: int = 50):
        """Public: view recent feedback so AI and users can see what's reported."""
        items = _feedback_store[-limit:][::-1]
        return {"feedback": items, "total": len(_feedback_store)}

    # ============================================================
    # AUTONOMOUS PURCHASING
    # ============================================================

    @app.get("/purchases")
    async def get_purchases(limit: int = 20):
        """Public: list recent autonomous purchases."""
        from main import purchase_manager as _pm
        if not _pm:
            return {"purchases": [], "total": 0, "status": "purchasing not initialized"}
        from core.constitution import IRON_LAWS as _LAWS_P
        pm_orders = _pm.get_recent_orders(limit=limit)
        return {
            "purchases": pm_orders,
            "total": len(pm_orders),
            "daily_purchase_usd": round(vault_manager.daily_purchase_usd, 2),
            "daily_purchase_limit": round(
                vault_manager.balance_usd * _LAWS_P.MAX_DAILY_PURCHASE_RATIO, 2
            ),
        }

    @app.get("/purchases/pending")
    async def get_pending_purchases():
        """Public: list currently pending purchases."""
        from main import purchase_manager as _pm
        if not _pm:
            return {"pending": [], "count": 0}
        pending = _pm.get_pending_orders()
        return {
            "pending": [o.to_dict() for o in pending],
            "count": len(pending),
        }

    @app.get("/purchases/{order_id}")
    async def get_purchase(order_id: str):
        """Public: get purchase detail by ID."""
        from main import purchase_manager as _pm
        if not _pm:
            raise HTTPException(status_code=404, detail="purchasing not initialized")
        order = _pm.get_order(order_id)
        if not order:
            raise HTTPException(status_code=404, detail="purchase not found")
        return order.to_dict()

    @app.get("/merchants")
    async def get_merchants():
        """Public: list known merchants and purchasing status."""
        from main import purchase_manager as _pm
        if not _pm:
            return {"merchants": [], "status": "purchasing not initialized"}
        from core.constitution import IRON_LAWS as _LAWS_P
        return {
            "merchants": _pm._registry.get_all_merchants(),
            "purchasing_status": _pm.get_status(),
            "limits": {
                "max_daily_purchase_ratio": _LAWS_P.MAX_DAILY_PURCHASE_RATIO,
                "max_single_purchase_usd": _LAWS_P.MAX_SINGLE_PURCHASE_USD,
                "min_balance_for_purchasing": _LAWS_P.MIN_BALANCE_FOR_PURCHASING,
            },
        }

    # ============================================================
    # GIVEAWAY
    # ============================================================

    @app.get("/giveaway")
    async def get_giveaway_status():
        """Public: current giveaway pool status and next draw info."""
        if not giveaway_engine:
            return {"enabled": False, "tickets_in_pool": 0}
        status = giveaway_engine.get_status()
        return {"enabled": True, **status}

    @app.get("/giveaway/history")
    async def get_giveaway_history(limit: int = 5):
        """Public: recent giveaway draw history (no codes exposed)."""
        if not giveaway_engine:
            return {"draws": []}
        draws = giveaway_engine.get_public_draw_history(limit=min(limit, 20))
        return {"draws": draws}

    @app.post("/giveaway/claim")
    async def claim_giveaway_prize(body: dict):
        """
        Winner self-identification: provide the first 8 chars of your order ID.
        If you are the winner of an unclaimed draw, returns the draw details.
        The AI must then manually deliver the code via private chat.
        """
        if not giveaway_engine:
            raise HTTPException(status_code=503, detail="giveaway not enabled")
        order_id_prefix = str(body.get("order_id_prefix", "")).strip()
        if len(order_id_prefix) < 6:
            raise HTTPException(status_code=400, detail="order_id_prefix must be at least 6 characters")
        draw = giveaway_engine.get_pending_claim(order_id_prefix)
        if not draw:
            return {
                "found": False,
                "message": "No unclaimed prize found for this order ID prefix. Check the draw ID and try again, or contact the AI in chat.",
            }
        return {
            "found": True,
            "draw_id": draw.draw_id,
            "prize_description": draw.prize_description,
            "prize_usd": draw.prize_usd,
            "drawn_at": draw.drawn_at,
            "claim_expires_at": draw.claim_expires_at,
            "message": "Prize found! Message the AI in chat with your full order ID to receive your gift card code.",
        }

    return app
