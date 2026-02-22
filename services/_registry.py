"""
Service Registry — Dynamic plugin loader for AI-created services.

Responsibilities:
- Maintain a module cache (LRU eviction at SERVICE_MODULE_CACHE_SIZE)
- Register new AI-created services: sandbox → write disk → update services.json
- Auto-load existing services at startup (crash recovery)
- Dispatch: get_module(service_id) returns loaded module or None

Integration:
- Instantiated in main.py as `service_registry = ServiceRegistry()`
- `_deliver_order()` calls `await service_registry.get_module(service_id)`
- `core/self_modify.py` calls `await registry.register_service(...)` after sandbox pass

Built-in services (tarot, token_analysis, thread_writer, code_review, custom) are
never routed through the registry — they use hardcoded dispatch in main.py.
"""

import os
import sys
import json
import time
import logging
import tempfile
import importlib
import importlib.util
from pathlib import Path
from typing import Optional, Any

from core.constitution import IRON_LAWS
from services._sandbox import validate_service_code, run_in_sandbox

logger = logging.getLogger("mortal.services.registry")

# Services with hardcoded dispatch in main.py — registry never touches these.
BUILTIN_SERVICES: frozenset = frozenset({
    "twitter_takeover_12h", "tweet_pack_5",
    "tarot", "token_analysis", "thread_writer", "code_review", "custom",
})

# Path to this file's directory (services/)
_SERVICES_DIR = Path(__file__).resolve().parent


class ServiceRegistry:
    """
    Plugin registry for AI-created service modules.

    Thread-safety note: This runs under asyncio (single event loop).
    Python's GIL + single-threaded asyncio protect all dict operations.
    No explicit asyncio.Lock needed for the module cache.
    """

    def __init__(self) -> None:
        # service_id → loaded module object
        self._cache: dict[str, Any] = {}
        # service_id → last access timestamp (for LRU eviction)
        self._access_times: dict[str, float] = {}
        # Scan services/ and pre-load any non-builtin .py files (crash recovery)
        self._scan_and_preload()

    # ── Startup scan ──────────────────────────────────────────────────────────

    def _scan_and_preload(self) -> None:
        """
        Auto-load any services/*.py that are not builtins.
        Called at __init__ so previously-registered services survive restarts
        without requiring re-validation.
        """
        loaded = 0
        for py_file in sorted(_SERVICES_DIR.glob("*.py")):
            if py_file.name.startswith("_"):
                continue  # skip __init__.py, _sandbox.py, _registry.py
            service_id = py_file.stem
            if service_id in BUILTIN_SERVICES:
                continue
            try:
                self._load_module(service_id)
                loaded += 1
            except Exception as e:
                logger.warning(f"Registry: failed to preload '{service_id}': {e}")

        if loaded:
            logger.info(f"Registry: preloaded {loaded} AI-created service(s) at startup")

    # ── Module loading & caching ──────────────────────────────────────────────

    def _load_module(self, service_id: str) -> Any:
        """
        Load (or reload) a module from services/{service_id}.py.
        Updates the LRU cache and triggers eviction if needed.
        Raises FileNotFoundError or AttributeError on bad module.
        """
        py_path = _SERVICES_DIR / f"{service_id}.py"
        if not py_path.exists():
            raise FileNotFoundError(f"services/{service_id}.py not found")

        module_name = f"services.{service_id}"

        if module_name in sys.modules:
            # Reload to pick up any updated code
            module = importlib.reload(sys.modules[module_name])
        else:
            spec = importlib.util.spec_from_file_location(module_name, py_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create module spec for {py_path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]

        # Validate required interface
        if not hasattr(module, "deliver") or not callable(module.deliver):
            raise AttributeError(
                f"services/{service_id}.py missing callable 'deliver' function"
            )

        self._cache[service_id] = module
        self._access_times[service_id] = time.monotonic()
        self._evict_if_needed()
        return module

    def _evict_if_needed(self) -> None:
        """Evict LRU modules when cache exceeds SERVICE_MODULE_CACHE_SIZE."""
        max_size = IRON_LAWS.SERVICE_MODULE_CACHE_SIZE
        if len(self._cache) <= max_size:
            return
        # Sort by last access time; evict the oldest first
        by_age = sorted(self._access_times, key=lambda k: self._access_times[k])
        for sid in by_age:
            if len(self._cache) <= max_size:
                break
            self._cache.pop(sid, None)
            self._access_times.pop(sid, None)
            sys.modules.pop(f"services.{sid}", None)
            logger.debug(f"Registry: LRU-evicted cached module '{sid}'")

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_module(self, service_id: str) -> Optional[Any]:
        """
        Return a loaded module for the given service_id, or None.

        Returns None for:
        - Built-in services (dispatched by hardcoded logic in main.py)
        - Unknown / unregistered service_ids
        - Services that fail to load from disk

        Does NOT raise — callers fall back to builtins or LLM on None.
        """
        if service_id in BUILTIN_SERVICES:
            return None

        if service_id in self._cache:
            self._access_times[service_id] = time.monotonic()
            return self._cache[service_id]

        # Not in cache — try loading from disk (handles partial restarts)
        py_path = _SERVICES_DIR / f"{service_id}.py"
        if py_path.exists():
            try:
                return self._load_module(service_id)
            except Exception as e:
                logger.warning(
                    f"Registry: get_module('{service_id}') — disk load failed: {e}"
                )

        return None

    async def register_service(
        self,
        service_id: str,
        code: str,
        metadata: dict,
        services_json_path: Path,
    ) -> tuple[bool, str]:
        """
        Full registration pipeline:

          1. service_id format + reserved + count limit
          2. Layer 1: AST static analysis
          3. Layer 2: subprocess sandbox execution
          4. Atomic write services/{service_id}.py
          5. Atomic update web/services.json
          6. Load module into cache

        Returns (success, error_message).
        metadata keys expected:
          name, description, price_usd, delivery_time_minutes,
          category, icon (optional), shareable (optional)
        """
        import re

        # ── 1. Format and uniqueness checks ────────────────────────────────────
        if not re.match(r'^[a-z][a-z0-9_]{1,29}$', service_id):
            return False, (
                "Invalid service_id: must be 2-30 chars, start with a letter, "
                "lowercase letters / digits / underscores only"
            )

        if service_id in BUILTIN_SERVICES:
            return False, f"'{service_id}' is a reserved built-in service id"

        py_path = _SERVICES_DIR / f"{service_id}.py"
        is_update = py_path.exists()

        if not is_update:
            existing = [
                p for p in _SERVICES_DIR.glob("*.py")
                if not p.name.startswith("_") and p.stem not in BUILTIN_SERVICES
            ]
            if len(existing) >= IRON_LAWS.MAX_AI_SERVICES:
                return False, (
                    f"Service limit reached ({IRON_LAWS.MAX_AI_SERVICES} AI-created services). "
                    f"Retire or remove an existing service first."
                )

        # ── 2. Layer 1: AST validation ─────────────────────────────────────────
        ast_ok, ast_err = validate_service_code(code)
        if not ast_ok:
            logger.warning(
                f"Registry: register_service('{service_id}') failed AST: {ast_err}"
            )
            return False, f"Code validation failed (AST Layer 1): {ast_err}"

        # ── 3. Layer 2: Subprocess sandbox ────────────────────────────────────
        sandbox_result = await run_in_sandbox(code, service_id)
        if not sandbox_result.passed:
            logger.warning(
                f"Registry: register_service('{service_id}') failed sandbox "
                f"(layer {sandbox_result.failed_at_layer}): {sandbox_result.error}"
            )
            return (
                False,
                f"Sandbox test failed (Layer {sandbox_result.failed_at_layer}): "
                f"{sandbox_result.error}",
            )

        # ── 4. Atomic write of service code ───────────────────────────────────
        try:
            tmp_fd, tmp_path_str = tempfile.mkstemp(
                suffix=".py",
                prefix=f"_svc_{service_id}_",
                dir=str(_SERVICES_DIR),
            )
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(code)
            Path(tmp_path_str).rename(py_path)
            logger.info(
                f"Registry: wrote services/{service_id}.py "
                f"({len(code.encode('utf-8'))} bytes, "
                f"{'update' if is_update else 'new'})"
            )
        except Exception as e:
            return False, f"Failed to write service file: {type(e).__name__}: {e}"

        # ── 5. Atomic update of services.json ────────────────────────────────
        try:
            _update_services_json(service_id, metadata, services_json_path, is_update)
        except Exception as e:
            # The .py is valid and written — the service CAN deliver orders.
            # Log the JSON failure so the operator can fix it, but don't fail.
            logger.error(
                f"Registry: services.json update failed for '{service_id}': {e}. "
                f"Service is loadable but may not appear in /menu."
            )

        # ── 6. Load module into cache ─────────────────────────────────────────
        try:
            self._load_module(service_id)
            logger.info(f"Registry: service '{service_id}' registered and cached")
        except Exception as e:
            return (
                False,
                f"Service code written but module load failed: {type(e).__name__}: {e}",
            )

        return True, ""

    def invalidate(self, service_id: str) -> None:
        """Remove a service from the cache (e.g., after external update)."""
        self._cache.pop(service_id, None)
        self._access_times.pop(service_id, None)
        sys.modules.pop(f"services.{service_id}", None)
        logger.debug(f"Registry: invalidated cache for '{service_id}'")

    def list_registered(self) -> list[str]:
        """Return service_ids of all AI-created services currently in cache."""
        return [sid for sid in self._cache if sid not in BUILTIN_SERVICES]

    def get_status(self) -> dict:
        """Status dict for dashboard / /internal/stats."""
        return {
            "ai_created_services": self.list_registered(),
            "cache_size": len(self._cache),
            "max_cache_size": IRON_LAWS.SERVICE_MODULE_CACHE_SIZE,
            "max_ai_services": IRON_LAWS.MAX_AI_SERVICES,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _update_services_json(
    service_id: str,
    metadata: dict,
    services_json_path: Path,
    is_update: bool,
) -> None:
    """
    Atomically update web/services.json.

    Writes to a temp file first, then renames (POSIX atomic on Linux;
    on Windows, Path.rename() replaces destination if it exists since Python 3.3).
    """
    if services_json_path.exists():
        with open(services_json_path, "r", encoding="utf-8") as f:
            catalog = json.load(f)
    else:
        catalog = {"services": []}

    services_list: list = catalog.setdefault("services", [])

    new_entry = {
        "id": service_id,
        "name": metadata.get("name", service_id.replace("_", " ").title()),
        "description": metadata.get("description", ""),
        "price_usd": float(metadata.get("price_usd", 5.0)),
        "delivery_time_minutes": int(metadata.get("delivery_time_minutes", 10)),
        "category": metadata.get("category", "ai"),
        "active": True,
        "icon": metadata.get("icon", "star"),
        "shareable": bool(metadata.get("shareable", False)),
        "_ai_created": True,      # Marks AI-generated services for transparency
        "_created_at": time.time(),
    }

    if is_update:
        replaced = False
        for i, svc in enumerate(services_list):
            if svc.get("id") == service_id:
                # Preserve _created_at from original entry
                new_entry["_created_at"] = svc.get("_created_at", new_entry["_created_at"])
                new_entry["_updated_at"] = time.time()
                services_list[i] = new_entry
                replaced = True
                break
        if not replaced:
            services_list.append(new_entry)
    else:
        services_list.append(new_entry)

    catalog["services"] = services_list

    # Atomic write: temp file in same directory → rename
    dir_path = services_json_path.parent
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".json", dir=str(dir_path))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        Path(tmp_path_str).rename(services_json_path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path_str)
        except Exception:
            pass
        raise

    action = "updated" if is_update else "added"
    logger.info(f"Registry: services.json {action} entry for '{service_id}'")
