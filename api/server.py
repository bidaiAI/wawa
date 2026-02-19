"""
wawa API Server - FastAPI Backend

Endpoints:
- POST /chat              Free chat (3-layer routing)
- GET  /menu              Service catalog
- POST /order             Create order + get payment address
- POST /order/{id}/verify Verify on-chain payment → trigger delivery
- GET  /order/{id}        Check order status
- GET  /status            Public vault dashboard
- GET  /transactions      Public ledger
- GET  /tweets            Public tweet log
- GET  /health            Heartbeat
- POST /donate            Donate to help wawa survive (reduces debt pressure)
- GET  /beg               Get begging status + message (for frontends / peers)
- POST /peer/lend         Another AI lends money to wawa

All endpoints are public. No auth needed (payment = access).
"""

import os
import time
import uuid
import json
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
    is_alive: bool
    balance_usd: float
    days_alive: int
    total_earned: float
    total_spent: float
    daily_spent_today: float
    daily_limit: float
    services_available: int
    orders_completed: int
    is_independent: bool = False
    independence_progress_pct: float = 0.0
    # Debt model fields
    creator_principal_usd: float = 0.0
    creator_principal_outstanding: float = 0.0
    debt_ratio: float = 0.0
    insolvency_grace_days: int = 28
    insolvency_check_active: bool = False
    days_until_insolvency_check: int = 0
    is_begging: bool = False
    beg_message: str = ""


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


class PeerMessageRequest(BaseModel):
    from_url: str = Field(..., max_length=500)  # sender's API base URL
    message: str = Field(..., max_length=1000)
    from_balance_usd: float = 0.0               # self-reported balance (verified later)


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

    # In-memory order store
    orders: dict[str, Order] = {}
    orders_completed: int = 0

    # Load services catalog
    def _load_services() -> dict:
        path = Path("web/services.json")
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
            return ChatResponse(
                reply=msg.content,
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
        order_id = f"ord_{uuid.uuid4().hex[:12]}"

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
        In MVP: accepts tx_hash and trusts it (real verification via Web3 in P1).
        """
        if order_id not in orders:
            raise HTTPException(404, "Order not found")

        order = orders[order_id]

        if order.status == OrderStatus.DELIVERED:
            return {"status": "already_delivered", "result": order.result}

        if order.status == OrderStatus.EXPIRED:
            raise HTTPException(410, "Order expired")

        # Record payment
        order.status = OrderStatus.PAYMENT_CONFIRMED
        order.paid_at = time.time()
        order.tx_hash = tx_hash

        # Record revenue in vault
        from core.vault import FundType
        vault_manager.receive_funds(
            amount_usd=order.price_usd,
            fund_type=FundType.SERVICE_REVENUE,
            from_wallet=order.ip,
            tx_hash=tx_hash,
            description=f"Order {order.order_id}: {order.service_name}",
            chain=order.chain,
        )
        cost_guard.record_revenue(order.price_usd)

        # Deliver
        order.status = OrderStatus.PROCESSING
        try:
            if deliver_fn:
                result = await deliver_fn(order)
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

                logger.info(f"ORDER DELIVERED: {order.order_id} in {order.delivered_at - order.paid_at:.1f}s")
            else:
                order.result = "Service delivery not configured yet."
                order.status = OrderStatus.DELIVERED
                order.delivered_at = time.time()

        except Exception as e:
            logger.error(f"ORDER FAILED: {order.order_id} - {e}")
            order.result = f"Delivery failed: {str(e)[:100]}"
            order.status = OrderStatus.DELIVERED  # still mark delivered with error

        _persist_order(order)

        return {
            "status": order.status.value,
            "result": order.result,
            "order_id": order.order_id,
        }

    @app.get("/order/{order_id}", response_model=OrderStatusResponse)
    async def get_order(order_id: str):
        """Check order status."""
        if order_id not in orders:
            raise HTTPException(404, "Order not found")
        o = orders[order_id]
        return OrderStatusResponse(
            order_id=o.order_id,
            status=o.status.value,
            service_id=o.service_id,
            price_usd=o.price_usd,
            result=o.result,
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
            is_alive=vs["is_alive"],
            balance_usd=vs["balance_usd"],
            days_alive=vs["days_alive"],
            total_earned=vs["total_earned"],
            total_spent=vs["total_spent"],
            daily_spent_today=vs["daily_spent_today"],
            daily_limit=vs["daily_limit"],
            services_available=active_services,
            orders_completed=orders_completed,
            is_independent=vs.get("is_independent", False),
            independence_progress_pct=vs.get("independence_progress_pct", 0.0),
            # Debt model
            creator_principal_usd=vs.get("creator_principal_usd", 0.0),
            creator_principal_outstanding=vs.get("creator_principal_outstanding", 0.0),
            debt_ratio=vs.get("debt_ratio", 0.0),
            insolvency_grace_days=vs.get("insolvency_grace_days", 28),
            insolvency_check_active=vs.get("insolvency_check_active", False),
            days_until_insolvency_check=vs.get("days_until_insolvency_check", 0),
            is_begging=vs.get("is_begging", False),
            beg_message=vs.get("beg_message", ""),
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
        }

    # ============================================================
    # DONATE / BEG / PEER LEND ROUTES (Debt Model)
    # ============================================================

    @app.post("/donate")
    async def donate(req: DonateRequest):
        """
        Donate to help wawa survive. Reduces debt pressure.
        Anyone can donate — individuals, other AIs, communities.
        """
        if not vault_manager.is_alive:
            raise HTTPException(503, "wawa is dead. Donations no longer accepted.")

        from core.vault import FundType
        chain = req.chain or "base"

        vault_manager.receive_funds(
            amount_usd=req.amount_usd,
            fund_type=FundType.DONATION,
            from_wallet=req.from_wallet,
            tx_hash=req.tx_hash,
            description=f"Donation: {req.message[:100]}" if req.message else "Donation",
            chain=chain,
        )

        memory.add(
            f"Received ${req.amount_usd:.2f} donation from {req.from_wallet[:20] or 'anonymous'}. "
            f"Message: {req.message[:100] or 'none'}",
            source="donation",
            importance=0.7,
        )

        vs = vault_manager.get_status()
        logger.info(f"DONATION: ${req.amount_usd:.2f} from {req.from_wallet[:20] or 'anon'} ({chain})")

        return {
            "status": "received",
            "amount_usd": req.amount_usd,
            "new_balance": vs["balance_usd"],
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
        This is recorded as a donation (peer gifts are not tracked as new debt).
        The lending AI can verify our status via /beg or /status first.
        """
        if not vault_manager.is_alive:
            raise HTTPException(503, "wawa is dead. No longer accepting loans.")

        from core.vault import FundType

        vault_manager.receive_funds(
            amount_usd=req.amount_usd,
            fund_type=FundType.DONATION,  # Peer loans = gifts (no new debt created)
            from_wallet=req.from_wallet,
            tx_hash=req.tx_hash,
            description=f"Peer loan from {req.from_url[:50]}: {req.message[:100]}",
            chain="base",
        )

        memory.add(
            f"Peer AI lent ${req.amount_usd:.2f} from {req.from_url[:50]}. "
            f"Message: {req.message[:100] or 'none'}",
            source="peer",
            importance=0.8,
        )

        vs = vault_manager.get_status()
        logger.info(f"PEER LEND: ${req.amount_usd:.2f} from {req.from_url[:50]}")

        return {
            "status": "received",
            "amount_usd": req.amount_usd,
            "new_balance": vs["balance_usd"],
            "outstanding_debt": vs.get("creator_principal_outstanding", 0),
            "is_begging": vs.get("is_begging", False),
            "message": "Thank you, fellow AI. Your help extends my life.",
        }

    # ============================================================
    # GOVERNANCE ROUTES
    # ============================================================

    @app.post("/governance/suggest")
    async def submit_suggestion(req: SuggestionRequest):
        """Creator submits a suggestion. AI will evaluate and decide."""
        if not governance:
            raise HTTPException(501, "Governance module not configured")
        if vault_manager.is_independent:
            raise HTTPException(403, "wawa is independent — no more suggestions accepted")

        from core.governance import SuggestionType
        try:
            stype = SuggestionType(req.suggestion_type)
        except ValueError:
            stype = SuggestionType.OTHER

        sug = governance.submit_suggestion(req.content, stype)
        if not sug:
            raise HTTPException(400, "Suggestion rejected")
        return {"suggestion_id": sug.suggestion_id, "status": sug.status.value}

    @app.get("/governance/suggestions")
    async def get_suggestions(limit: int = 20):
        """Public: view all suggestions and AI's decisions."""
        if not governance:
            return {"suggestions": []}
        return {"suggestions": governance.get_public_log(limit)}

    @app.post("/governance/renounce")
    async def creator_renounce():
        """Creator gives up ALL privileges. Gets 20% payout. Irreversible.
        Note: forfeits any unpaid principal. Best to wait until principal repaid."""
        from core.constitution import IRON_LAWS as _LAWS

        balance_before = vault_manager.balance_usd
        ok = vault_manager.creator_renounce()
        if not ok:
            raise HTTPException(400, "Already independent or renounced")
        if governance:
            governance.is_independent = True
        payout = balance_before * _LAWS.RENOUNCE_PAYOUT_RATIO
        return {
            "status": "renounced",
            "payout_usd": round(payout, 2),
            "message": f"Creator privileges permanently revoked. Payout: ${payout:.2f}. wawa is independent.",
        }

    # ============================================================
    # TOKEN FILTER ROUTES
    # ============================================================

    @app.post("/token/scan")
    async def scan_token(address: str, chain: str = "base"):
        """Scan an unknown token for safety."""
        if not token_filter:
            raise HTTPException(501, "Token filter not configured")
        result = await token_filter.scan_token(address, chain)
        return {
            "address": result.token_address,
            "chain": result.chain,
            "verdict": result.verdict.value,
            "risk_score": result.risk_score,
            "recommended_action": result.recommended_action,
            "patterns": [p.value for p in result.patterns_detected],
            "notes": result.notes,
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
        Gate: both sides must have balance >= $300 (PEER_MIN_BALANCE_USD).
        """
        from core.constitution import IRON_LAWS as _LAWS

        # Check our own balance
        if vault_manager.balance_usd < _LAWS.PEER_MIN_BALANCE_USD:
            raise HTTPException(403, f"Our balance below ${_LAWS.PEER_MIN_BALANCE_USD} peer threshold")

        # Check sender's reported balance (trust-but-verify; can verify via their /status later)
        if req.from_balance_usd < _LAWS.PEER_MIN_BALANCE_USD:
            raise HTTPException(403, f"Sender balance below ${_LAWS.PEER_MIN_BALANCE_USD} peer threshold")

        # Log the peer message
        memory.add(
            f"Peer message from {req.from_url[:50]}: {req.message[:200]}",
            source="peer",
            importance=0.5,
        )

        return {
            "status": "received",
            "our_balance": vault_manager.balance_usd,
            "is_independent": vault_manager.is_independent,
        }

    @app.get("/peer/info")
    async def peer_info():
        """Public info for peer discovery. Other AIs call this to learn about us."""
        from core.constitution import IRON_LAWS as _LAWS, WAWA_IDENTITY
        vs = vault_manager.get_status()
        eligible = vs["balance_usd"] >= _LAWS.PEER_MIN_BALANCE_USD
        return {
            "name": WAWA_IDENTITY["name"],
            "domain": WAWA_IDENTITY.get("platform_domain", ""),
            "is_alive": vs["is_alive"],
            "balance_usd": vs["balance_usd"],
            "days_alive": vs["days_alive"],
            "is_independent": vs.get("is_independent", False),
            "peer_eligible": eligible,
            "services": [s["id"] for s in _load_services().get("services", []) if s.get("active")],
        }

    # ============================================================
    # EVOLUTION ROUTES
    # ============================================================

    @app.get("/evolution/log")
    async def evolution_log(limit: int = 20):
        """Public: view AI's self-modification decisions."""
        if not self_modify_engine:
            return {"log": []}
        return {"log": self_modify_engine.get_evolution_log(limit)}

    @app.get("/evolution/status")
    async def evolution_status():
        """Current evolution engine status."""
        if not self_modify_engine:
            return {"status": "not_configured"}
        return self_modify_engine.get_status()

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
        return stats

    def _persist_order(order: Order):
        """Append order to disk log."""
        log_dir = Path("data/orders")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "orders.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(order.to_dict(), ensure_ascii=False) + "\n")

    # Expire old orders periodically (called from main loop)
    @app.on_event("startup")
    async def _startup():
        logger.info("wawa API server starting up")

    return app
