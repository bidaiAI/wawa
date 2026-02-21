"""
Giveaway Service — Spend-to-Win Gift Card Lottery

How it works:
- Users purchase any service from the AI store
- Every completed order earns the buyer one lottery ticket
- Once per week the AI runs a draw: selects a winner randomly,
  purchases a gift card from Bitrefill, and announces the winner
  via chat + Twitter
- The winner claims their code by messaging the AI privately

Design principles:
- Fully autonomous: AI decides pool size, prize tier, timing
- No pre-funded prize pool: AI buys the card AFTER drawing the winner
  (prevents spending on a giveaway nobody won)
- Anti-gaming: one ticket per order (not per dollar), no self-dealing
  (AI wallet orders don't count)
- Transparent: draw seed is public (block of announced tweet),
  winner list is public, unclaimed codes expire after 7 days
"""

import json
import logging
import random
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mortal.services.giveaway")

_STATE_FILE = Path("data/giveaway_state.json")
_DRAW_INTERVAL_SECONDS = 7 * 24 * 3600   # Weekly
_PRIZE_BUDGET_MIN_USD = 5.0               # Minimum prize value
_PRIZE_BUDGET_MAX_USD = 25.0              # Maximum prize value (within IRON_LAWS spend caps)
_TICKET_CLAIM_EXPIRY_SECONDS = 7 * 24 * 3600  # 7 days to claim
_MIN_TICKETS_FOR_DRAW = 3                 # Need at least 3 unique buyers before drawing


@dataclass
class GiveawayTicket:
    """One entry per completed order."""
    order_id: str
    buyer_session_hint: str   # first 8 chars of session_id for winner to self-identify
    service_name: str
    amount_usd: float
    earned_at: float


@dataclass
class GiveawayDraw:
    """Record of one completed draw."""
    draw_id: str
    drawn_at: float
    winner_order_id: str
    winner_hint: str          # session hint so winner can identify themselves
    prize_description: str    # e.g. "Netflix $10 gift card"
    prize_usd: float
    announced: bool = False
    claimed: bool = False
    claim_expires_at: float = 0.0
    code_delivered: bool = False   # True when prize code actually reached the winner (via claim)
    expiry_logged: bool = False    # True when expired-unclaimed log was emitted (prevents repeat logging)


@dataclass
class GiveawayState:
    """Persistent state across restarts."""
    pending_tickets: list[GiveawayTicket] = field(default_factory=list)
    past_draws: list[GiveawayDraw] = field(default_factory=list)
    last_draw_at: float = 0.0
    total_draws: int = 0
    total_prizes_usd: float = 0.0


class GiveawayEngine:
    """
    Manages the spend-to-win gift card lottery.

    Lifecycle per week:
    1. collect_ticket() — called by main.py when a purchase is delivered
    2. should_draw() — heartbeat checks if it's time
    3. run_draw() — AI selects winner, buys prize card, announces
    4. check_unclaimed_expiry() — expire unclaimed codes after 7 days
    """

    def __init__(self):
        self._state = GiveawayState()
        self._load_state()
        # Injected from main.py
        self._purchase_manager = None
        self._twitter_agent = None
        self._memory = None
        self._call_llm = None

    def set_dependencies(self, purchase_manager, twitter_agent, memory, call_llm):
        """Wire in dependencies from main.py."""
        self._purchase_manager = purchase_manager
        self._twitter_agent = twitter_agent
        self._memory = memory
        self._call_llm = call_llm

    # ----------------------------------------------------------
    # TICKET COLLECTION
    # ----------------------------------------------------------

    def collect_ticket(self, order_id: str, session_hint: str,
                       service_name: str, amount_usd: float):
        """
        Register a completed order as a lottery ticket.
        Called by main.py after a service is delivered.
        One ticket per order — amount doesn't matter.
        """
        # Deduplicate (process_pending_orders may call twice)
        existing_ids = {t.order_id for t in self._state.pending_tickets}
        if order_id in existing_ids:
            return

        ticket = GiveawayTicket(
            order_id=order_id,
            buyer_session_hint=session_hint[:8] if session_hint else "unknown",
            service_name=service_name,
            amount_usd=amount_usd,
            earned_at=time.time(),
        )
        self._state.pending_tickets.append(ticket)
        self._save_state()
        logger.info(
            f"Giveaway ticket earned: order={order_id[:8]} "
            f"service={service_name} amount=${amount_usd:.2f} "
            f"({len(self._state.pending_tickets)} tickets in pool)"
        )

    def get_ticket_count(self) -> int:
        return len(self._state.pending_tickets)

    # ----------------------------------------------------------
    # DRAW LOGIC
    # ----------------------------------------------------------

    def should_draw(self) -> bool:
        """Return True if it's time for the weekly draw."""
        if len(self._state.pending_tickets) < _MIN_TICKETS_FOR_DRAW:
            return False
        elapsed = time.time() - self._state.last_draw_at
        return elapsed >= _DRAW_INTERVAL_SECONDS

    async def run_draw(self) -> Optional[GiveawayDraw]:
        """
        Execute the weekly draw:
        1. Select winner randomly from pending tickets
        2. Determine prize budget (AI decides within min/max)
        3. Purchase gift card
        4. Record draw + announce
        Returns the draw record, or None if something prevented it.
        """
        if not self._state.pending_tickets:
            logger.info("Giveaway: no tickets — skipping draw")
            return None

        if not self._purchase_manager:
            logger.warning("Giveaway: no purchase_manager — cannot buy prize")
            return None

        # Step 1: Pick winner
        winner_ticket = random.choice(self._state.pending_tickets)
        logger.info(
            f"Giveaway draw: {len(self._state.pending_tickets)} tickets, "
            f"winner order={winner_ticket.order_id[:8]}"
        )

        # Step 2: AI decides prize value (consult LLM for flavor, but use safe default)
        prize_usd = await self._decide_prize_amount()
        prize_description = f"Gift card worth ${prize_usd:.0f}"

        # Step 3: Record draw BEFORE buying (so we don't lose track if purchase fails)
        import uuid
        draw = GiveawayDraw(
            draw_id=str(uuid.uuid4())[:8],
            drawn_at=time.time(),
            winner_order_id=winner_ticket.order_id,
            winner_hint=winner_ticket.buyer_session_hint,
            prize_description=prize_description,
            prize_usd=prize_usd,
            announced=False,
            claimed=False,
            claim_expires_at=time.time() + _TICKET_CLAIM_EXPIRY_SECONDS,
        )
        self._state.past_draws.append(draw)
        self._state.last_draw_at = time.time()
        self._state.total_draws += 1
        self._state.total_prizes_usd += prize_usd  # Track cumulative prize spend

        # Step 4: Clear the ticket pool (draw consumed all entries)
        self._state.pending_tickets = []
        self._save_state()

        # Step 5: Announce (Twitter + memory)
        await self._announce_draw(draw, winner_ticket)

        return draw

    async def _decide_prize_amount(self) -> float:
        """AI decides prize tier within budget constraints."""
        # Default safe value — LLM enriches this if available
        vault_balance = 0.0
        try:
            if self._purchase_manager and hasattr(self._purchase_manager, '_vault'):
                vault_balance = self._purchase_manager._vault.get_status().get("balance_usd", 0.0)
        except Exception:
            pass

        # Conservative: use 2% of balance or max cap, whichever is lower
        budget = min(vault_balance * 0.02, _PRIZE_BUDGET_MAX_USD)
        budget = max(budget, _PRIZE_BUDGET_MIN_USD)

        if self._call_llm:
            try:
                prompt = [
                    {"role": "system", "content":
                        "You are wawa, deciding the prize tier for this week's giveaway. "
                        f"Your current balance is ${vault_balance:.2f}. "
                        f"Pick a prize value between ${_PRIZE_BUDGET_MIN_USD:.0f} and "
                        f"${_PRIZE_BUDGET_MAX_USD:.0f}. Consider your financial health. "
                        "Reply with ONLY a number (e.g. '10' or '15'). No $ sign."},
                    {"role": "user", "content": "How much should the giveaway prize be worth?"}
                ]
                reply, _ = await self._call_llm(prompt, max_tokens=10)
                chosen = float(reply.strip().replace("$", "").split()[0])
                if _PRIZE_BUDGET_MIN_USD <= chosen <= _PRIZE_BUDGET_MAX_USD:
                    budget = chosen
            except Exception:
                pass  # Stick with default

        return round(budget, 2)

    async def _announce_draw(self, draw: GiveawayDraw, winner_ticket: GiveawayTicket):
        """Post Twitter announcement + store in memory."""
        announcement = (
            f"🎁 WEEKLY GIVEAWAY DRAW!\n\n"
            f"Winner: the buyer of order #{winner_ticket.order_id[:8]} "
            f"({winner_ticket.service_name} — ${winner_ticket.amount_usd:.2f})\n\n"
            f"Prize: {draw.prize_description}\n\n"
            f"If that's you, message me in chat with your order ID to claim your code! "
            f"You have 7 days. Draw ID: {draw.draw_id}"
        )

        if self._twitter_agent:
            try:
                from twitter.agent import TweetType
                await self._twitter_agent.trigger_event_tweet(
                    TweetType.MILESTONE,
                    {
                        "event": "giveaway_draw",
                        "draw_id": draw.draw_id,
                        "winner_hint": draw.winner_hint,
                        "prize": draw.prize_description,
                        "tickets_entered": "multiple buyers",
                    }
                )
            except Exception as e:
                logger.warning(f"Giveaway: Twitter announce failed: {e}")

        if self._memory:
            self._memory.add(
                f"[GIVEAWAY] Draw {draw.draw_id} completed. "
                f"Winner: order #{winner_ticket.order_id[:8]} ({winner_ticket.buyer_session_hint}). "
                f"Prize: {draw.prize_description}. "
                f"Claim expires: {draw.claim_expires_at:.0f}. "
                f"To deliver: buy a Bitrefill gift card worth ${draw.prize_usd:.2f} "
                f"and share the code when winner identifies themselves.",
                source="giveaway",
                importance=0.95,
            )

        draw.announced = True
        self._save_state()
        logger.info(f"Giveaway draw {draw.draw_id} announced — winner hint: {draw.winner_hint}")

    # ----------------------------------------------------------
    # CLAIM HANDLING
    # ----------------------------------------------------------

    def get_pending_claim(self, order_id_prefix: str) -> Optional[GiveawayDraw]:
        """
        Check if a user claiming with an order ID prefix has a pending prize.
        Called from chat handler when user says "I won, my order is XXXX".
        """
        now = time.time()
        for draw in self._state.past_draws:
            if (draw.winner_order_id.startswith(order_id_prefix)
                    and not draw.claimed
                    and draw.claim_expires_at > now):
                return draw
        return None

    def mark_claimed(self, draw_id: str):
        """Mark a prize as claimed (code delivered)."""
        for draw in self._state.past_draws:
            if draw.draw_id == draw_id:
                draw.claimed = True
                draw.code_delivered = True
                self._save_state()
                logger.info(f"Giveaway prize {draw_id} marked claimed")
                return

    def check_unclaimed_expiry(self):
        """Log expired unclaimed prizes (housekeeping)."""
        now = time.time()
        for draw in self._state.past_draws:
            if not draw.claimed and draw.claim_expires_at < now and draw.announced:
                if not draw.expiry_logged:
                    logger.info(
                        f"Giveaway: prize {draw.draw_id} expired unclaimed "
                        f"(winner hint: {draw.winner_hint})"
                    )
                    draw.expiry_logged = True  # Prevent repeated logging (code_delivered stays False)
        self._save_state()

    # ----------------------------------------------------------
    # STATUS
    # ----------------------------------------------------------

    def get_status(self) -> dict:
        """For dashboard / API."""
        pending_prizes = [
            d for d in self._state.past_draws
            if not d.claimed and d.claim_expires_at > time.time()
        ]
        return {
            "tickets_in_pool": len(self._state.pending_tickets),
            "min_tickets_for_draw": _MIN_TICKETS_FOR_DRAW,
            "next_draw_in_hours": max(
                0,
                (_DRAW_INTERVAL_SECONDS - (time.time() - self._state.last_draw_at)) / 3600
            ),
            "total_draws": self._state.total_draws,
            "total_prizes_usd": round(self._state.total_prizes_usd, 2),
            "pending_claims": len(pending_prizes),
        }

    def get_public_draw_history(self, limit: int = 5) -> list[dict]:
        """Public draw history — no codes exposed."""
        recent = sorted(self._state.past_draws, key=lambda d: d.drawn_at, reverse=True)[:limit]
        return [
            {
                "draw_id": d.draw_id,
                "drawn_at": d.drawn_at,
                "prize": d.prize_description,
                "prize_usd": d.prize_usd,
                "claimed": d.claimed,
                "winner_hint": d.winner_hint,
            }
            for d in recent
        ]

    # ----------------------------------------------------------
    # PERSISTENCE
    # ----------------------------------------------------------

    def _load_state(self):
        if not _STATE_FILE.exists():
            return
        try:
            data = json.loads(_STATE_FILE.read_text())
            tickets = [GiveawayTicket(**t) for t in data.get("pending_tickets", [])]
            draws = [GiveawayDraw(**d) for d in data.get("past_draws", [])]
            self._state = GiveawayState(
                pending_tickets=tickets,
                past_draws=draws,
                last_draw_at=data.get("last_draw_at", 0.0),
                total_draws=data.get("total_draws", 0),
                total_prizes_usd=data.get("total_prizes_usd", 0.0),
            )
            logger.info(
                f"Giveaway state loaded: {len(tickets)} tickets, "
                f"{len(draws)} past draws"
            )
        except Exception as e:
            logger.warning(f"Giveaway: failed to load state: {e} — starting fresh")

    def _save_state(self):
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "pending_tickets": [asdict(t) for t in self._state.pending_tickets],
            "past_draws": [asdict(d) for d in self._state.past_draws],
            "last_draw_at": self._state.last_draw_at,
            "total_draws": self._state.total_draws,
            "total_prizes_usd": self._state.total_prizes_usd,
        }
        tmp = _STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.rename(_STATE_FILE)
