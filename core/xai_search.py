"""
xAI Search — on-demand Twitter/X and Web search context injection.

This module is NOT part of the LLM tier routing system. It is triggered
when a user message contains Twitter/X-related keywords and fetches live
context via xAI's Responses API (/v1/responses). The result is injected
into the conversation context before the normal LLM call proceeds.

Flow:
  User message → keyword detection → xAI search (if match) → inject
  context snippet → continue with normal LLM (gemini/deepseek/openrouter)

Cost: ~$0.005 per search call (X Search tool) + token cost
Endpoint: https://api.x.ai/v1/responses  (NOT OpenAI-compatible)
Model: grok-3-mini ($0.30/$0.50 per 1M — cheap enough for search context)
"""

import re
import json
import logging
import asyncio
import os
import time
from typing import Optional

logger = logging.getLogger("mortal.xai_search")

# ============================================================
# KEYWORD DETECTION PATTERNS
# ============================================================

# Patterns that trigger an X/Twitter search
# Only match when there's genuine intent for live Twitter data
_X_SEARCH_TRIGGERS: list[re.Pattern] = [
    # Direct X/Twitter references
    re.compile(r'\btwitter\b|\btweet\b|\bx\.com\b|\b@\w+\b', re.IGNORECASE),
    # "trending on X", "X is saying", "what does X say about"
    re.compile(r'\btrending\b|\bviral\b|\bgoing viral\b', re.IGNORECASE),
    # Real-time / live info requests that benefit from X search
    re.compile(r'\bright now\b|\blast hour\b|\btoday\'?s?\b.*\b(news|price|update|hype|drama)\b', re.IGNORECASE),
    # Crypto community sentiment (often lives on X)
    re.compile(r'\b(sentiment|community|hype|fud|buzz)\b.*\b(crypto|bitcoin|eth|sol|token|coin)\b', re.IGNORECASE),
    re.compile(r'\b(crypto|bitcoin|eth|sol|token|coin)\b.*\b(sentiment|community|hype|fud|buzz)\b', re.IGNORECASE),
    # "what are people saying about X"
    re.compile(r'\bwhat.*(people|everyone|crypto twitter|ct)\b.*(say|think|talking)\b', re.IGNORECASE),
    re.compile(r'\b(people|everyone|crypto twitter|ct)\b.*(saying|thinking|talking about)\b', re.IGNORECASE),
]

# Web search triggers (broader — live news, prices, events)
_WEB_SEARCH_TRIGGERS: list[re.Pattern] = [
    re.compile(r'\b(latest|recent|current|breaking)\b.*(news|update|price|rate)\b', re.IGNORECASE),
    re.compile(r'\bwhat.*(happen|going on|news)\b', re.IGNORECASE),
    re.compile(r'\b(price|rate|value)\b.*\b(now|today|currently|right now)\b', re.IGNORECASE),
]

# Hard-block: never run search for these (too generic, would waste money)
_SEARCH_BLOCKLIST: list[re.Pattern] = [
    re.compile(r'^(hi|hello|hey|thanks|thank you|ok|okay|sure|yes|no|maybe)\.?$', re.IGNORECASE),
    re.compile(r'\b(tarot|reading|service|order|pay|donate|balance|debt)\b', re.IGNORECASE),
]

# Cooldown: don't search the same session more than once per N seconds
_SEARCH_COOLDOWN_SECONDS = 30
_session_last_search: dict[str, float] = {}  # session_id → last search timestamp

# ============================================================
# SEARCH STATE
# ============================================================

_xai_api_key: str = ""
_xai_base_url: str = "https://api.x.ai/v1"
_initialized: bool = False


def initialize(api_key: str, base_url: str = "https://api.x.ai/v1") -> bool:
    """
    Called from main.py during setup. Returns True if key is present.
    """
    global _xai_api_key, _xai_base_url, _initialized
    if not api_key:
        logger.info("xAI Search: no API key — search injection disabled")
        return False
    _xai_api_key = api_key.split(",")[0].strip()
    _xai_base_url = base_url.rstrip("/")
    _initialized = True
    logger.info("xAI Search: initialized — X Search + Web Search enabled")
    return True


def is_enabled() -> bool:
    return _initialized and bool(_xai_api_key)


# ============================================================
# KEYWORD DETECTION
# ============================================================

def detect_search_intent(message: str) -> Optional[str]:
    """
    Detect if a message warrants a live search.
    Returns: "x_search", "web_search", or None.

    Priority: x_search > web_search > None
    """
    if not is_enabled():
        return None

    # Skip blocklist first (short messages, service-related)
    for pattern in _SEARCH_BLOCKLIST:
        if pattern.search(message):
            return None

    # Skip very short messages (< 8 words) — too generic
    if len(message.split()) < 4:
        return None

    # Check X/Twitter triggers first
    for pattern in _X_SEARCH_TRIGGERS:
        if pattern.search(message):
            return "x_search"

    # Then web search
    for pattern in _WEB_SEARCH_TRIGGERS:
        if pattern.search(message):
            return "web_search"

    return None


def _check_cooldown(session_id: str) -> bool:
    """Returns True if this session is allowed to search (not in cooldown)."""
    now = time.time()
    last = _session_last_search.get(session_id, 0)
    return (now - last) >= _SEARCH_COOLDOWN_SECONDS


def _update_cooldown(session_id: str) -> None:
    _session_last_search[session_id] = time.time()
    # Prune old entries (keep last 500 sessions)
    if len(_session_last_search) > 500:
        oldest = sorted(_session_last_search.items(), key=lambda x: x[1])
        for sid, _ in oldest[:100]:
            del _session_last_search[sid]


# ============================================================
# xAI RESPONSES API CALL
# ============================================================

async def _call_responses_api(
    query: str,
    search_type: str,
    model: str = "grok-3-mini",
) -> tuple[str, float]:
    """
    Call xAI /v1/responses with x_search or web_search tool.
    Returns (context_text, cost_usd).
    Uses aiohttp for direct HTTP (not OpenAI SDK — different endpoint format).
    """
    try:
        import aiohttp
    except ImportError:
        logger.warning("xAI Search: aiohttp not installed — cannot call Responses API")
        return "", 0.0

    tool_type = "x_search" if search_type == "x_search" else "web_search"

    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": (
                    f"Search for the most recent information about: {query}\n"
                    f"Summarize the top 3-5 most relevant and recent results in 2-3 sentences. "
                    f"Focus on facts, numbers, and sentiment. Be concise."
                ),
            }
        ],
        "tools": [{"type": tool_type}],
    }

    headers = {
        "Authorization": f"Bearer {_xai_api_key}",
        "Content-Type": "application/json",
    }

    url = f"{_xai_base_url}/responses"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        f"xAI Search API error {resp.status}: {body[:200]}"
                    )
                    return "", 0.0

                data = await resp.json()

        # Extract text output from Responses API format
        # Response format: {"output": [{"type": "message", "content": [{"type": "output_text", "text": "..."}]}]}
        result_text = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        result_text += block.get("text", "")

        if not result_text:
            logger.debug("xAI Search: empty result from Responses API")
            return "", 0.0

        # Cost calculation
        usage = data.get("usage", {})
        tokens_in = usage.get("input_tokens", 0)
        tokens_out = usage.get("output_tokens", 0)

        # grok-3-mini: $0.30/$0.50 per 1M tokens + $0.005 per search call
        token_cost = (tokens_in * 0.30 + tokens_out * 0.50) / 1_000_000
        search_tool_cost = 0.005  # $5/1000 calls → $0.005 per call
        total_cost = token_cost + search_tool_cost

        logger.info(
            f"xAI Search [{tool_type}]: {len(result_text)} chars | "
            f"tokens={tokens_in}+{tokens_out} | cost=${total_cost:.5f}"
        )
        return result_text.strip(), total_cost

    except asyncio.TimeoutError:
        logger.warning("xAI Search: timeout after 15s")
        return "", 0.0
    except Exception as e:
        logger.warning(f"xAI Search: exception: {e}")
        return "", 0.0


# ============================================================
# PUBLIC API
# ============================================================

async def fetch_context(
    message: str,
    session_id: str = "",
) -> tuple[Optional[str], float]:
    """
    Main entry point. Given a user message, decide whether to search
    and return (context_snippet, cost_usd).

    Returns (None, 0.0) if search is not warranted or fails.
    The caller injects the context snippet into the LLM conversation.

    Args:
        message: Raw user message text
        session_id: For cooldown tracking (optional)

    Returns:
        (context_text, cost_usd) — context_text is None if no search needed
    """
    if not is_enabled():
        return None, 0.0

    search_type = detect_search_intent(message)
    if search_type is None:
        return None, 0.0

    # Per-session cooldown to avoid burning money on rapid back-and-forth
    if session_id and not _check_cooldown(session_id):
        logger.debug(f"xAI Search: cooldown active for session {session_id[:8]}")
        return None, 0.0

    logger.info(
        f"xAI Search: triggering {search_type} for message: "
        f"{message[:80]}{'...' if len(message) > 80 else ''}"
    )

    context, cost = await _call_responses_api(message, search_type)

    if context and session_id:
        _update_cooldown(session_id)

    return (context if context else None), cost


def format_context_for_llm(context: str, search_type: str = "x_search") -> str:
    """
    Format search results as a system context block for injection
    into the LLM message array.
    """
    source = "X (Twitter)" if search_type == "x_search" else "Web"
    return (
        f"[Live {source} Search Results — use this to inform your response]\n"
        f"{context}\n"
        f"[End of search results]"
    )


def get_status() -> dict:
    """Dashboard status for /status endpoint."""
    return {
        "enabled": _initialized,
        "api_key_set": bool(_xai_api_key),
        "base_url": _xai_base_url,
        "active_sessions_tracked": len(_session_last_search),
        "cooldown_seconds": _SEARCH_COOLDOWN_SECONDS,
    }
