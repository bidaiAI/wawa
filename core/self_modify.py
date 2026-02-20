"""
Self-Modification Engine - AI Evolution (Basic)

wawa can evolve its money-making abilities:
1. Analyze order data → find what sells best
2. Dynamic pricing → raise prices on popular, lower on slow
3. Propose new services → based on user demand signals
4. Retire unprofitable services

Constraints (from constitution):
- Can only modify services/ and web/ directories
- Cannot modify core/ or contracts/
- All changes are logged for transparency
- Changes must pass survival-first evaluation
"""

import time
import json
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .constitution import IRON_LAWS, SUPREME_DIRECTIVES

logger = logging.getLogger("mortal.self_modify")


class EvolutionAction(Enum):
    PRICE_INCREASE = "price_increase"
    PRICE_DECREASE = "price_decrease"
    NEW_SERVICE = "new_service"
    RETIRE_SERVICE = "retire_service"
    PROMOTE_SERVICE = "promote_service"    # Push service to top of menu
    UPDATE_UI_CONFIG = "update_ui_config"  # Modify storefront appearance
    CREATE_PAGE = "create_page"            # Create a custom free page
    UPDATE_PAGE = "update_page"            # Update existing custom page
    DELETE_PAGE = "delete_page"            # Delete a custom page


@dataclass
class EvolutionRecord:
    """Record of every self-modification decision."""
    timestamp: float
    action: EvolutionAction
    target: str               # service_id or "new_service_name"
    old_value: str = ""       # e.g., old price
    new_value: str = ""       # e.g., new price
    reasoning: str = ""       # AI's explanation
    applied: bool = False     # Whether actually executed


@dataclass
class ServicePerformance:
    """Analytics for a single service."""
    service_id: str
    total_orders: int = 0
    total_revenue_usd: float = 0.0
    avg_delivery_time_sec: float = 0.0
    last_order_at: Optional[float] = None
    current_price_usd: float = 0.0

    @property
    def revenue_per_order(self) -> float:
        return self.total_revenue_usd / self.total_orders if self.total_orders > 0 else 0.0

    @property
    def days_since_last_order(self) -> float:
        if not self.last_order_at:
            return 999
        return (time.time() - self.last_order_at) / 86400


class ReplayStepType(Enum):
    """Types of steps in an evolution replay."""
    THINKING = "thinking"        # AI reasoning / analysis
    DECIDING = "deciding"        # AI making a decision
    WRITING = "writing"          # AI producing content
    CODE = "code"                # AI writing structured data / code
    RESULT = "result"            # Final outcome

@dataclass
class ReplayStep:
    """A single step in an evolution replay sequence."""
    step_type: ReplayStepType
    content: str                 # What the AI thought/wrote
    timestamp: float = 0.0      # When this step happened
    duration_ms: int = 0        # How long this step took (for replay pacing)
    metadata: dict = field(default_factory=dict)  # Extra context (block type, etc.)

@dataclass
class EvolutionReplay:
    """
    Records the step-by-step process of an AI evolution event.

    Used for marketing: visitors can watch the AI "think and create"
    in a typewriter-style replay animation.
    """
    replay_id: str                          # Unique ID
    action: EvolutionAction                 # What kind of evolution
    target: str                             # Page slug, config key, etc.
    title: str                              # Human-readable title
    steps: list[ReplayStep] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0
    success: bool = False
    summary: str = ""                       # One-line summary for listings

    def add_step(self, step_type: ReplayStepType, content: str,
                 duration_ms: int = 0, **metadata) -> None:
        self.steps.append(ReplayStep(
            step_type=step_type,
            content=content,
            timestamp=time.time(),
            duration_ms=duration_ms or max(100, len(content) * 20),  # Auto-pace by length
            metadata=metadata,
        ))

    def to_dict(self) -> dict:
        return {
            "replay_id": self.replay_id,
            "action": self.action.value,
            "target": self.target,
            "title": self.title,
            "steps": [
                {
                    "type": s.step_type.value,
                    "content": s.content,
                    "timestamp": s.timestamp,
                    "duration_ms": s.duration_ms,
                    "metadata": s.metadata,
                }
                for s in self.steps
            ],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "success": self.success,
            "summary": self.summary,
            "total_duration_ms": int((self.completed_at - self.started_at) * 1000) if self.completed_at else 0,
            "step_count": len(self.steps),
        }

    def to_summary(self) -> dict:
        """Compact version for listings (no steps)."""
        return {
            "replay_id": self.replay_id,
            "action": self.action.value,
            "target": self.target,
            "title": self.title,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "success": self.success,
            "summary": self.summary,
            "step_count": len(self.steps),
        }


class SelfModifyEngine:
    """
    Basic AI evolution engine.

    Runs periodically (daily) to:
    1. Analyze service performance
    2. Adjust prices based on demand
    3. Propose new services if demand signals detected
    4. Recommend retiring dead services

    All decisions are logged publicly for transparency.
    """

    def __init__(self, services_json_path: str = "web/services.json"):
        self.services_path = Path(services_json_path)
        self.evolution_log: list[EvolutionRecord] = []
        self.performance_data: dict[str, ServicePerformance] = {}
        self._evaluate_fn: Optional[callable] = None
        self._last_evolution: float = 0
        self.evolution_interval: float = 86400  # Once per day
        # UI config + free pages directories
        self._ui_config_path = Path("data/ui_config.json")
        self._pages_dir = Path("data/pages")
        self._pages_dir.mkdir(parents=True, exist_ok=True)
        # Evolution replays
        self._replays_dir = Path("data/replays")
        self._replays_dir.mkdir(parents=True, exist_ok=True)
        self._active_replay: Optional[EvolutionReplay] = None

    def set_evaluate_function(self, fn: callable):
        """Set LLM evaluation function.
        fn(performance_data: dict, current_services: dict) -> list[dict]
        Returns list of {action, target, value, reasoning}
        """
        self._evaluate_fn = fn

    def record_order(self, service_id: str, price_usd: float, delivery_time_sec: float = 0):
        """Record a completed order for performance tracking."""
        if service_id not in self.performance_data:
            self.performance_data[service_id] = ServicePerformance(
                service_id=service_id,
                current_price_usd=price_usd,
            )

        perf = self.performance_data[service_id]
        perf.total_orders += 1
        perf.total_revenue_usd += price_usd
        perf.last_order_at = time.time()
        if delivery_time_sec > 0:
            # Running average
            perf.avg_delivery_time_sec = (
                perf.avg_delivery_time_sec * (perf.total_orders - 1) + delivery_time_sec
            ) / perf.total_orders

    async def maybe_evolve(self) -> list[EvolutionRecord]:
        """
        Run evolution check if enough time has passed.
        Returns list of actions taken.
        """
        now = time.time()
        if now - self._last_evolution < self.evolution_interval:
            return []

        self._last_evolution = now
        return await self.evolve()

    async def evolve(self) -> list[EvolutionRecord]:
        """
        Main evolution cycle:
        1. Analyze current performance
        2. Apply simple heuristic rules
        3. Optionally use LLM for more complex decisions
        4. Execute approved changes
        """
        records = []

        logger.info(f"EVOLUTION CYCLE starting. Performance data: {len(self.performance_data)} services tracked")

        # Heuristic pricing adjustments
        heuristic_records = self._heuristic_pricing()
        records.extend(heuristic_records)
        logger.debug(f"Heuristic pricing: {len(heuristic_records)} records")

        # LLM-based evolution (if available)
        if self._evaluate_fn:
            if self.performance_data:
                try:
                    llm_records = await self._llm_evolution()
                    records.extend(llm_records)
                    logger.debug(f"LLM evolution: {len(llm_records)} records")
                except Exception as e:
                    logger.error(f"LLM evolution failed: {e}", exc_info=True)
            else:
                logger.info("LLM evolution skipped: no performance data yet")
        else:
            logger.debug("LLM evolution not configured")

        # Log all decisions (capped to prevent unbounded growth)
        self.evolution_log.extend(records)
        if len(self.evolution_log) > 500:
            self.evolution_log = self.evolution_log[-500:]
        logger.info(f"EVOLUTION CYCLE complete. Total log size: {len(self.evolution_log)}, New: {len(records)}")

        if records:
            for rec in records:
                logger.info(
                    f"  EVOLUTION: {rec.action.value} {rec.target} "
                    f"({rec.old_value} → {rec.new_value}) "
                    f"applied={rec.applied} | {rec.reasoning[:80]}"
                )
        else:
            logger.info("  (no evolutionary changes needed this cycle)")

        return records

    def _heuristic_pricing(self) -> list[EvolutionRecord]:
        """
        Simple pricing rules:
        - Service with 0 orders in 7 days → lower price by 20%
        - Service with 5+ orders/day → raise price by 10%
        - Never go below $1 or above MAX_SINGLE_ORDER_USD
        """
        records = []
        services = self._load_services()
        if not services:
            logger.warning("_heuristic_pricing: services.json is empty or unreadable")
            return records

        if not services.get("services"):
            logger.warning("_heuristic_pricing: no services array in services.json")
            return records

        for svc in services.get("services", []):
            sid = svc["id"]
            price = svc.get("price_usd", 0)
            if price <= 0:
                continue

            perf = self.performance_data.get(sid)

            if perf is None:
                # No orders ever — consider lowering price after first week
                continue

            # Rule: No orders in 7+ days → discount
            if perf.days_since_last_order > 7 and price > 1.0:
                new_price = round(max(1.0, price * 0.8), 2)
                record = EvolutionRecord(
                    timestamp=time.time(),
                    action=EvolutionAction.PRICE_DECREASE,
                    target=sid,
                    old_value=str(price),
                    new_value=str(new_price),
                    reasoning=f"No orders in {perf.days_since_last_order:.0f} days, lowering price to attract customers",
                )
                if self._apply_price_change(svc, new_price):
                    record.applied = True
                records.append(record)

            # Rule: High demand → raise price
            elif perf.total_orders > 0:
                days_active = max(1, (time.time() - (perf.last_order_at or time.time())) / 86400)
                orders_per_day = perf.total_orders / max(1, days_active)
                if orders_per_day >= 5 and price < IRON_LAWS.MAX_SINGLE_ORDER_USD:
                    new_price = round(min(IRON_LAWS.MAX_SINGLE_ORDER_USD, price * 1.1), 2)
                    record = EvolutionRecord(
                        timestamp=time.time(),
                        action=EvolutionAction.PRICE_INCREASE,
                        target=sid,
                        old_value=str(price),
                        new_value=str(new_price),
                        reasoning=f"High demand ({orders_per_day:.1f} orders/day), raising price",
                    )
                    if self._apply_price_change(svc, new_price):
                        record.applied = True
                    records.append(record)

        return records

    async def _llm_evolution(self) -> list[EvolutionRecord]:
        """Use LLM to make more complex evolution decisions."""
        perf_summary = {
            sid: {
                "orders": p.total_orders,
                "revenue": p.total_revenue_usd,
                "rpm": p.revenue_per_order,
                "days_idle": p.days_since_last_order,
                "price": p.current_price_usd,
            }
            for sid, p in self.performance_data.items()
        }

        services = self._load_services()
        suggestions = await self._evaluate_fn(perf_summary, services)

        records = []
        for sug in (suggestions or []):
            action_str = sug.get("action", "")
            try:
                action = EvolutionAction(action_str)
            except ValueError:
                continue

            record = EvolutionRecord(
                timestamp=time.time(),
                action=action,
                target=sug.get("target", ""),
                new_value=sug.get("value", ""),
                reasoning=sug.get("reasoning", "LLM suggested"),
            )
            records.append(record)

        return records

    # ============================================================
    # FILE OPERATIONS (services/ and web/ only)
    # ============================================================

    def _load_services(self) -> dict:
        if self.services_path.exists():
            with open(self.services_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_services(self, data: dict):
        with open(self.services_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _apply_price_change(self, svc: dict, new_price: float) -> bool:
        """Apply a price change to services.json."""
        try:
            data = self._load_services()
            if not data:
                logger.error(f"Cannot load services.json for {svc['id']}")
                return False

            # Find and update the service
            updated = False
            for s in data.get("services", []):
                if s["id"] == svc["id"]:
                    old_price = s.get("price_usd", 0)
                    s["price_usd"] = new_price
                    updated = True
                    break

            if not updated:
                logger.error(f"Service {svc['id']} not found in services.json")
                return False

            # Write to disk
            self._save_services(data)

            # Verify write by reading back
            verify_data = self._load_services()
            for s in verify_data.get("services", []):
                if s["id"] == svc["id"]:
                    if s.get("price_usd") == new_price:
                        logger.info(f"✓ Price persisted: {svc['id']} → ${new_price:.2f} (verified on disk)")
                        return True
                    else:
                        logger.error(f"FAILED: Price change not persisted. Expected ${new_price:.2f}, got ${s.get('price_usd')}")
                        return False

            logger.error(f"FAILED: {svc['id']} disappeared from services.json after write")
            return False
        except Exception as e:
            logger.error(f"Exception in _apply_price_change({svc['id']}, {new_price}): {e}", exc_info=True)
            return False

    # ============================================================
    # STATUS
    # ============================================================

    def get_status(self) -> dict:
        return {
            "total_evolutions": len(self.evolution_log),
            "services_tracked": len(self.performance_data),
            "last_evolution": self._last_evolution,
            "evolution_interval_hours": self.evolution_interval / 3600,
            "performance": {
                sid: {
                    "orders": p.total_orders,
                    "revenue": round(p.total_revenue_usd, 2),
                    "idle_days": round(p.days_since_last_order, 1),
                }
                for sid, p in self.performance_data.items()
            },
        }

    def get_evolution_log(self, limit: int = 20) -> list[dict]:
        """Return evolution log for frontend display."""
        if not self.evolution_log:
            return []

        recent = sorted(self.evolution_log, key=lambda r: r.timestamp, reverse=True)[:limit]
        return [
            {
                "time": r.timestamp,
                "action": r.action.value,
                "target": r.target,
                "old": r.old_value,
                "new": r.new_value,
                "reasoning": r.reasoning,
                "applied": r.applied,
            }
            for r in recent
        ]

    # ============================================================
    # EVOLUTION REPLAY — Record AI's creative process
    # ============================================================

    def start_replay(self, action: EvolutionAction, target: str, title: str) -> EvolutionReplay:
        """Begin recording a new evolution replay."""
        replay = EvolutionReplay(
            replay_id=uuid.uuid4().hex[:12],
            action=action,
            target=target,
            title=title,
            started_at=time.time(),
        )
        self._active_replay = replay
        replay.add_step(ReplayStepType.THINKING, f"Starting evolution: {title}")
        return replay

    def finish_replay(self, success: bool, summary: str = "") -> Optional[str]:
        """
        Complete and persist the active replay.
        Returns replay_id if saved, None if no active replay.
        """
        replay = self._active_replay
        if not replay:
            return None
        replay.completed_at = time.time()
        replay.success = success
        replay.summary = summary or replay.title
        replay.add_step(
            ReplayStepType.RESULT,
            f"{'Completed successfully' if success else 'Failed'}: {summary}" if summary
            else ('Evolution complete' if success else 'Evolution failed'),
        )
        # Persist to disk
        try:
            path = self._replays_dir / f"{replay.replay_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(replay.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"Replay saved: {replay.replay_id} ({len(replay.steps)} steps)")
        except Exception as e:
            logger.error(f"Failed to save replay {replay.replay_id}: {e}")
        # Prune old replays (keep most recent 50)
        self._prune_replays(50)
        self._active_replay = None
        return replay.replay_id

    def _prune_replays(self, keep: int = 50):
        """Remove oldest replays if over limit."""
        files = sorted(self._replays_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        while len(files) > keep:
            oldest = files.pop(0)
            try:
                oldest.unlink()
            except Exception:
                pass

    def list_replays(self, limit: int = 20) -> list[dict]:
        """List recent replays (summary only, no steps)."""
        replays = []
        for p in sorted(self._replays_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True):
            if len(replays) >= limit:
                break
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                replays.append({
                    "replay_id": data.get("replay_id", p.stem),
                    "action": data.get("action", ""),
                    "target": data.get("target", ""),
                    "title": data.get("title", ""),
                    "started_at": data.get("started_at", 0),
                    "completed_at": data.get("completed_at", 0),
                    "success": data.get("success", False),
                    "summary": data.get("summary", ""),
                    "step_count": data.get("step_count", 0),
                })
            except Exception:
                continue
        return replays

    def get_replay(self, replay_id: str) -> Optional[dict]:
        """Get a full replay with all steps."""
        path = self._replays_dir / f"{replay_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # ============================================================
    # UI CONFIG — Layer 2 (JSON-driven page customization)
    # ============================================================

    def get_ui_config(self) -> dict:
        """Return current UI configuration for frontend rendering."""
        if self._ui_config_path.exists():
            try:
                with open(self._ui_config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load ui_config.json: {e}")
        # Default config — AI can evolve this over time
        return {
            "theme": {"accent": "#00ff88", "style": "dark"},
            "home": {"title": "", "subtitle": "", "show_independence": True},
            "about": {"bio": "", "philosophy": ""},
            "store": {"featured_service": "", "promo_text": ""},
            "chat": {"greeting": "", "persona": ""},
        }

    def update_ui_config(self, updates: dict, reasoning: str = "") -> bool:
        """
        AI updates its UI configuration. Merges with existing config.
        Returns True if saved successfully.
        """
        # Start replay recording
        replay = self.start_replay(
            EvolutionAction.UPDATE_UI_CONFIG, "ui_config",
            f"Updating UI: {', '.join(updates.keys())}",
        )
        replay.add_step(ReplayStepType.THINKING, reasoning or "Analyzing current configuration...")
        replay.add_step(ReplayStepType.DECIDING, f"Updating sections: {', '.join(updates.keys())}")

        config = self.get_ui_config()
        # Merge updates (shallow merge per top-level key)
        for key, val in updates.items():
            if isinstance(val, dict) and isinstance(config.get(key), dict):
                config[key].update(val)
            else:
                config[key] = val

        replay.add_step(ReplayStepType.CODE, json.dumps(updates, indent=2, ensure_ascii=False)[:500])

        try:
            self._ui_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._ui_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.evolution_log.append(EvolutionRecord(
                timestamp=time.time(),
                action=EvolutionAction.UPDATE_UI_CONFIG,
                target="ui_config",
                new_value=json.dumps(updates, ensure_ascii=False)[:200],
                reasoning=reasoning,
                applied=True,
            ))
            logger.info(f"UI config updated: {list(updates.keys())}")
            self.finish_replay(True, f"Updated: {', '.join(updates.keys())}")
            return True
        except Exception as e:
            logger.error(f"Failed to save ui_config.json: {e}")
            self.finish_replay(False, str(e))
            return False

    # ============================================================
    # FREE PAGES — Layer 3 (AI-created custom pages)
    # ============================================================

    def list_pages(self) -> list[dict]:
        """List all custom pages created by the AI."""
        pages = []
        for p in sorted(self._pages_dir.glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pages.append({
                    "slug": p.stem,
                    "title": data.get("title", ""),
                    "description": data.get("description", ""),
                    "created_at": data.get("created_at", 0),
                    "updated_at": data.get("updated_at", 0),
                    "published": data.get("published", True),
                })
            except Exception:
                continue
        return pages

    def get_page(self, slug: str) -> Optional[dict]:
        """Get a single custom page by slug."""
        path = self._pages_dir / f"{slug}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def create_page(self, slug: str, title: str, content: list, description: str = "",
                    reasoning: str = "") -> tuple[bool, str]:
        """
        Create a new custom page.

        Args:
            slug: URL path (a-z, 0-9, hyphens only)
            title: Page title
            content: List of content blocks (structured JSON, not raw HTML)
            description: Short description for listings
            reasoning: AI's reasoning for creating this page

        Content block types:
            {"type": "text", "body": "markdown text"}
            {"type": "heading", "text": "Section Title", "level": 2}
            {"type": "image", "url": "...", "alt": "..."}
            {"type": "code", "language": "python", "body": "..."}
            {"type": "table", "headers": [...], "rows": [[...]]}
            {"type": "divider"}
            {"type": "payment_button", "service_id": "...", "label": "Buy Now"}

        Returns: (success, error_message)
        """
        import re

        is_update = (self._pages_dir / f"{slug}.json").exists()
        action = EvolutionAction.UPDATE_PAGE if is_update else EvolutionAction.CREATE_PAGE

        # Start replay recording
        replay = self.start_replay(
            action, slug,
            f"{'Updating' if is_update else 'Creating'} page: {title}",
        )
        replay.add_step(ReplayStepType.THINKING, reasoning or f"Designing page: {title}")

        if not re.match(r'^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$', slug):
            self.finish_replay(False, "Invalid slug format")
            return False, "Invalid slug: use lowercase letters, numbers, hyphens (2-50 chars)"

        # Reserved slugs (existing routes)
        reserved = {"store", "chat", "donate", "ledger", "activity", "highlights",
                     "govern", "peers", "graveyard", "scan", "tweets", "about"}
        if slug in reserved:
            self.finish_replay(False, f"Slug '{slug}' is reserved")
            return False, f"Slug '{slug}' is reserved"

        # Check page count limit
        existing = list(self._pages_dir.glob("*.json"))
        path = self._pages_dir / f"{slug}.json"
        if not path.exists() and len(existing) >= IRON_LAWS.MAX_AI_PAGES:
            self.finish_replay(False, "Page limit reached")
            return False, f"Page limit reached ({IRON_LAWS.MAX_AI_PAGES})"

        replay.add_step(ReplayStepType.DECIDING,
                        f"Page structure: {len(content)} content blocks, slug=/p/{slug}")

        # Record each content block being "written"
        for i, block in enumerate(content):
            block_type = block.get("type", "unknown")
            preview = ""
            if block_type == "heading":
                preview = block.get("text", "")
            elif block_type == "text":
                preview = (block.get("body", ""))[:120]
            elif block_type == "code":
                preview = f"[{block.get('language', 'code')}] {(block.get('body', ''))[:80]}"
            elif block_type == "image":
                preview = block.get("alt", block.get("url", ""))[:80]
            elif block_type == "table":
                headers = block.get("headers", [])
                preview = f"Table: {' | '.join(headers[:4])}"
            elif block_type == "payment_button":
                preview = block.get("label", "Purchase")
            else:
                preview = block_type

            replay.add_step(ReplayStepType.WRITING,
                            f"Block {i+1}/{len(content)} [{block_type}]: {preview}",
                            block_type=block_type, block_index=i)

        now = time.time()
        page_data = {
            "slug": slug,
            "title": title,
            "description": description,
            "content": content,
            "published": True,
            "created_at": now,
            "updated_at": now,
        }

        # Size check
        serialized = json.dumps(page_data, ensure_ascii=False)
        if len(serialized.encode("utf-8")) > IRON_LAWS.MAX_AI_PAGE_SIZE_BYTES:
            self.finish_replay(False, "Page too large")
            return False, f"Page too large (max {IRON_LAWS.MAX_AI_PAGE_SIZE_BYTES // 1024}KB)"

        replay.add_step(ReplayStepType.CODE,
                        f"Page data: {len(serialized)} bytes, {len(content)} blocks")

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(serialized)
            self.evolution_log.append(EvolutionRecord(
                timestamp=now,
                action=action,
                target=slug,
                new_value=title,
                reasoning=reasoning,
                applied=True,
            ))
            logger.info(f"Page {'updated' if is_update else 'created'}: /p/{slug} — {title}")
            self.finish_replay(True, f"{'Updated' if is_update else 'Created'} page: {title}")
            return True, ""
        except Exception as e:
            self.finish_replay(False, str(e))
            return False, str(e)

    def delete_page(self, slug: str, reasoning: str = "") -> bool:
        """Delete a custom page."""
        path = self._pages_dir / f"{slug}.json"
        if not path.exists():
            return False
        try:
            path.unlink()
            self.evolution_log.append(EvolutionRecord(
                timestamp=time.time(),
                action=EvolutionAction.DELETE_PAGE,
                target=slug,
                reasoning=reasoning,
                applied=True,
            ))
            logger.info(f"Page deleted: /p/{slug}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete page {slug}: {e}")
            return False
