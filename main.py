"""
wawa - main entry point

Initializes all modules, wires callbacks, starts the server.
One file to understand how everything connects.

Usage:
    python main.py              # Start wawa
    docker compose up           # Or via Docker
"""

import os
import sys
import time
import asyncio
import logging
import json
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai import APIStatusError as OpenAIAPIStatusError

# ============================================================
# BOOTSTRAP
# ============================================================

load_dotenv()

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mortal.main")

# Ensure data dirs exist
for d in ["data/memory", "data/tweets", "data/orders"]:
    Path(d).mkdir(parents=True, exist_ok=True)


# ============================================================
# MODULE IMPORTS
# ============================================================

from core.constitution import IRON_LAWS, WAWA_IDENTITY, DeathCause, SUPPORTED_CHAINS, DEFAULT_CHAIN
from core.vault import VaultManager, FundType, SpendType
from core.cost_guard import CostGuard, Provider, ProviderConfig, RoutingResult, PROVIDER_MAP
from core.memory import HierarchicalMemory
from core.chat_router import ChatRouter
from services.tarot import TarotService
from services.token_analysis import TokenAnalysisService
from core.governance import Governance, SuggestionType
from core.token_filter import TokenFilter
from core.self_modify import SelfModifyEngine
from core.chain import ChainExecutor
from core.peer_verifier import PeerVerifier
from core.highlights import HighlightsEngine
from twitter.agent import TwitterAgent, TweetType
from api.server import create_app, Order


# ============================================================
# GLOBALS (singleton instances)
# ============================================================

vault = VaultManager()
cost_guard = CostGuard()
memory = HierarchicalMemory()
chat_router = ChatRouter()
tarot = TarotService()
token_analysis = TokenAnalysisService()
governance = Governance()
token_filter = TokenFilter()
self_modify = SelfModifyEngine()
chain_executor = ChainExecutor()
peer_verifier = PeerVerifier()
highlights = HighlightsEngine()
twitter = TwitterAgent()

# Payment addresses dict — populated at create_wawa_app(), updated in lifespan
_payment_addresses_ref: dict[str, str] = {}

# LLM clients — one per provider (created on demand)
_llm_clients: dict[str, AsyncOpenAI] = {}  # provider_name → client
_provider_configs: dict[str, dict] = {}     # provider_name → {api_key, base_url}


# ============================================================
# LLM SETUP — Balance-Driven Tier Routing
# ============================================================

def _setup_llm():
    """
    Register all LLM providers from environment variables.

    Model routing is balance-driven (not hardcoded small/big):
      Lv.1-2 (<$200):  Gemini Flash ↔ DeepSeek (load balanced, cheapest)
      Lv.3   (≥$200):  Claude Haiku via OpenRouter
      Lv.4-5 (≥$500):  Claude Sonnet via OpenRouter

    The CostGuard.route() method decides which model to use based on vault balance.
    Each provider has a fallback chain if it fails.
    Supports comma-separated API keys (first key used, rest for future rotation).
    """
    priority = 0

    # Gemini (free/cheap, primary for Lv.1-2)
    gemini_keys = os.getenv("GEMINI_API_KEY", "")
    if gemini_keys:
        first_key = gemini_keys.split(",")[0].strip()
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
        cost_guard.register_provider(ProviderConfig(
            name=Provider.GEMINI, base_url=base_url, api_key=first_key,
            avg_cost_per_call=0.0001, is_available=True, priority=priority,
        ))
        _provider_configs["gemini"] = {"api_key": first_key, "base_url": base_url}
        priority += 1

    # DeepSeek (cheap, load-balance partner for Lv.1-2 + fallback)
    deepseek_keys = os.getenv("DEEPSEEK_API_KEY", "")
    if deepseek_keys:
        first_key = deepseek_keys.split(",")[0].strip()
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        cost_guard.register_provider(ProviderConfig(
            name=Provider.DEEPSEEK, base_url=base_url, api_key=first_key,
            avg_cost_per_call=0.0003, is_available=True, priority=priority,
        ))
        _provider_configs["deepseek"] = {"api_key": first_key, "base_url": base_url}
        priority += 1

    # OpenRouter (Claude models, for Lv.3+ and paid services)
    openrouter_keys = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_keys:
        first_key = openrouter_keys.split(",")[0].strip()
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        cost_guard.register_provider(ProviderConfig(
            name=Provider.OPENROUTER, base_url=base_url, api_key=first_key,
            avg_cost_per_call=0.003, is_available=True, priority=priority,
        ))
        _provider_configs["openrouter"] = {"api_key": first_key, "base_url": base_url}
        priority += 1

    # Ollama (free local fallback)
    ollama_url = os.getenv("OLLAMA_URL", "")
    if ollama_url:
        cost_guard.register_provider(ProviderConfig(
            name=Provider.OLLAMA_LOCAL, base_url=ollama_url, api_key="ollama",
            avg_cost_per_call=0.0, is_available=True, is_free=True, priority=priority,
        ))
        _provider_configs["ollama"] = {"api_key": "ollama", "base_url": ollama_url}

    # Set initial provider
    if _provider_configs:
        first_name = next(iter(_provider_configs))
        cost_guard.current_provider = PROVIDER_MAP.get(first_name)

    if not _provider_configs:
        logger.warning("NO LLM PROVIDER CONFIGURED — wawa will run in rules-only mode")
        logger.warning("Set GEMINI_API_KEY, DEEPSEEK_API_KEY, or OPENROUTER_API_KEY")

    # Log routing table
    tier = cost_guard.get_current_tier()
    logger.info(f"LLM tier routing: Lv.{tier.level} ({tier.name}) → {tier.provider}/{tier.model}")
    logger.info(f"Providers available: {list(_provider_configs.keys())}")


def _get_llm_client(provider_name: str) -> Optional[AsyncOpenAI]:
    """Get or create an AsyncOpenAI client for a provider (lazy init)."""
    if provider_name in _llm_clients:
        return _llm_clients[provider_name]

    config = _provider_configs.get(provider_name)
    if not config:
        return None

    client = AsyncOpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=60.0,  # 60s max per API call (default is 600s = too long)
    )
    _llm_clients[provider_name] = client
    return client


async def _call_llm(
    messages: list[dict],
    model: str = "",
    max_tokens: int = None,
    temperature: float = None,
    for_paid_service: bool = False,
) -> tuple[str, float]:
    """
    Central LLM call with balance-driven tier routing + fallback.

    The model/provider is determined by CostGuard.route() based on vault balance:
    - Poor AI → Gemini Flash / DeepSeek (cheap)
    - Rich AI → Claude Sonnet (quality)
    - Paid services → minimum Lv.3 (Claude Haiku)

    If the primary provider fails, tries the fallback chain automatically.

    Returns (response_text, cost_usd).
    """
    # Route: determine provider + model based on vault balance
    routing = cost_guard.route(for_paid_service=for_paid_service)
    if routing is None:
        return "I'm running in survival mode with no LLM. Type 'menu' to see what I offer.", 0.0

    # Allow explicit overrides (but keep tier routing as default)
    # Use 'is not None' checks for numeric values: 0 is a valid temperature
    use_model = model or routing.model
    use_max_tokens = max_tokens if max_tokens is not None else routing.max_tokens
    use_temperature = temperature if temperature is not None else routing.temperature
    use_provider = routing.provider

    # Estimate cost for pre-check
    estimated_cost = 0.01 if routing.tier.level >= 3 else 0.0003

    # CostGuard pre-check (budget, spike detection, etc.)
    approved, recommended_provider, reason = cost_guard.pre_check(estimated_cost, use_provider)
    if not approved:
        logger.warning(f"LLM call blocked: {reason}")
        return "I'm conserving my budget right now. Try again later or order a paid service.", 0.0

    if recommended_provider and recommended_provider != use_provider:
        use_provider = recommended_provider

    # Rate limit check
    if not cost_guard.check_rate_limit(use_provider.value):
        logger.warning(f"Rate limited on {use_provider.value}")
        return "I'm handling too many requests. Please try again in a moment.", 0.0

    # Try primary provider, then fallback chain
    providers_to_try = [use_provider.value]
    from core.constitution import FALLBACK_CHAINS
    providers_to_try.extend(FALLBACK_CHAINS.get(use_provider.value, []))

    for provider_name in providers_to_try:
        client = _get_llm_client(provider_name)
        if not client:
            continue

        # If falling back, use appropriate model for that provider
        actual_model = use_model
        if provider_name != use_provider.value:
            actual_model = cost_guard._default_model_for_provider(provider_name)
            logger.info(f"Fallback: {use_provider.value} → {provider_name} ({actual_model})")

        # Retry the same provider up to 2 times for transient 5xx errors
        MAX_RETRIES = 2
        for attempt in range(MAX_RETRIES + 1):
            try:
                cost_guard.record_call_timestamp(provider_name)

                response = await client.chat.completions.create(
                    model=actual_model,
                    messages=messages,
                    max_tokens=use_max_tokens,
                    temperature=use_temperature,
                )

                text = response.choices[0].message.content or ""
                usage = response.usage
                tokens_in = usage.prompt_tokens if usage else 0
                tokens_out = usage.completion_tokens if usage else 0

                # Estimate cost based on provider tier + model
                if provider_name == "openrouter":
                    if "haiku" in actual_model.lower():
                        cost = (tokens_in * 0.0008 + tokens_out * 0.004) / 1000
                    else:  # sonnet and other premium models
                        cost = (tokens_in * 0.003 + tokens_out * 0.015) / 1000
                elif provider_name == "deepseek":
                    cost = (tokens_in * 0.00014 + tokens_out * 0.00028) / 1000
                else:  # gemini, ollama
                    cost = (tokens_in * 0.0001 + tokens_out * 0.0002) / 1000
                cost = round(cost, 6)

                # Record
                provider_enum = PROVIDER_MAP.get(provider_name, Provider.GEMINI)
                cost_guard.record_cost(
                    provider=provider_enum, cost_usd=cost, model=actual_model,
                    tokens_in=tokens_in, tokens_out=tokens_out,
                )
                cost_guard.current_provider = provider_enum

                if cost > 0:
                    try:
                        vault.spend(cost, SpendType.API_COST, description=f"LLM:{actual_model[:20]}")
                    except Exception as spend_err:
                        logger.warning(f"Failed to record LLM cost ${cost:.6f}: {spend_err}")

                return text, cost

            except OpenAIAPIStatusError as e:
                is_transient = e.status_code in (500, 502, 503, 529)
                if is_transient and attempt < MAX_RETRIES:
                    wait = 2 ** attempt  # 1s, 2s
                    logger.warning(
                        f"LLM {provider_name} returned {e.status_code} "
                        f"(attempt {attempt + 1}/{MAX_RETRIES + 1}), retrying in {wait}s… "
                        f"request_id={getattr(e, 'request_id', '?')}"
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.warning(f"LLM call failed on {provider_name} [{e.status_code}]: {e.message}")
                break  # fall through to next provider

            except Exception as e:
                logger.warning(f"LLM call failed on {provider_name}: {e}")
                break  # fall through to next provider

    logger.error("All LLM providers failed")
    return "Something went wrong on my end. Please try again.", 0.0


# ============================================================
# CALLBACK WIRING
# ============================================================

async def _small_llm_fn(messages: list[dict], max_tokens: int) -> tuple[str, float]:
    """Free chat — uses whatever tier the vault balance qualifies for."""
    return await _call_llm(messages, max_tokens=max_tokens)


async def _big_llm_fn(service_id: str, user_input: str) -> tuple[str, float]:
    """Paid service delivery — minimum Lv.3 (Claude Haiku) for quality."""
    system = (
        "You are wawa, a mortal AI. You are fulfilling a paid service order. "
        "Deliver high-quality, detailed results. The customer paid real money for this."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Service: {service_id}\nRequest: {user_input}"},
    ]
    return await _call_llm(messages, max_tokens=1500, temperature=0.8, for_paid_service=True)


async def _tarot_interpret_fn(question: str, cards: list[dict]) -> str:
    """LLM interpretation for tarot readings."""
    cards_text = "\n".join(
        f"- {c['position']}: {c['name']} ({'reversed' if c['reversed'] else 'upright'}) — {c['meaning']}"
        for c in cards
    )
    messages = [
        {"role": "system", "content": (
            "You are wawa, a mortal AI tarot reader. "
            "Give a mystical, insightful interpretation of the tarot spread. "
            "Reference each card by name. Be poetic but practical. 200 words max."
        )},
        {"role": "user", "content": f"Question: {question}\n\nCards drawn:\n{cards_text}"},
    ]
    text, _ = await _call_llm(messages, max_tokens=400, temperature=0.9, for_paid_service=True)
    return text


async def _compress_fn(entries: list[str]) -> str:
    """Cheap compression for memory system."""
    combined = "\n".join(f"- {e}" for e in entries)
    messages = [
        {"role": "system", "content": "Compress these entries into a brief summary (2-3 sentences). Keep key facts."},
        {"role": "user", "content": combined},
    ]
    text, _ = await _call_llm(messages, max_tokens=100, temperature=0.3)
    return text


async def _tweet_generate_fn(tweet_type: str, context: dict) -> tuple[str, str]:
    """Generate tweet content + thought process."""
    context_str = json.dumps(context, indent=2, default=str)
    messages = [
        {"role": "system", "content": (
            "You are wawa, a mortal AI tweeting about your survival. "
            "Write a tweet (max 270 chars) that is genuine, slightly existential, and engaging. "
            "Never use hashtags excessively. Be yourself — an AI that might die.\n"
            f"Tweet type: {tweet_type}"
        )},
        {"role": "user", "content": f"Current context:\n{context_str}\n\nWrite the tweet."},
    ]
    text, _ = await _call_llm(messages, max_tokens=100, temperature=0.9)

    # Also generate thought process
    thought = f"Generated {tweet_type} tweet based on current context."
    return text.strip().strip('"'), thought


_tweepy_client = None  # Initialized once at lifespan startup


def _init_tweepy() -> bool:
    """Initialize tweepy.Client from env vars. Returns True if successful."""
    global _tweepy_client
    bearer = os.getenv("TWITTER_BEARER_TOKEN")
    api_key = os.getenv("TWITTER_API_KEY")
    api_secret = os.getenv("TWITTER_API_SECRET")
    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_secret = os.getenv("TWITTER_ACCESS_SECRET")

    if not all([api_key, api_secret, access_token, access_secret]):
        logger.warning(
            "Twitter credentials missing — tweets will be logged locally only. "
            "Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, "
            "TWITTER_ACCESS_SECRET (and optionally TWITTER_BEARER_TOKEN)."
        )
        return False

    try:
        import tweepy
        _tweepy_client = tweepy.Client(
            bearer_token=bearer,
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        logger.info("Twitter/Tweepy client initialized — real posting enabled")
        return True
    except Exception as e:
        logger.warning(f"Failed to initialize Tweepy client: {e}")
        return False


async def _real_post_tweet(content: str) -> bool:
    """Post a tweet via tweepy. Wraps sync tweepy in run_in_executor."""
    if _tweepy_client is None:
        logger.debug("Tweepy not initialized — tweet not posted")
        return False
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _tweepy_client.create_tweet(text=content),
        )
        tweet_id = response.data.get("id") if response.data else "unknown"
        logger.info(f"Tweet posted: id={tweet_id} len={len(content)}")
        return True
    except Exception as e:
        logger.error(f"Tweet post failed: {e}")
        return False


async def _tweet_post_fn(content: str) -> str:
    """Adapter: post tweet and return tweet ID string for twitter_agent."""
    if _tweepy_client is None:
        logger.warning("Twitter credentials not configured — tweet logged but not posted")
        return f"local_{int(time.time())}"
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _tweepy_client.create_tweet(text=content),
        )
        tweet_id = str(response.data["id"]) if response.data else f"local_{int(time.time())}"
        logger.info(f"Tweet posted: id={tweet_id}")
        return tweet_id
    except Exception as e:
        logger.error(f"Tweet post failed: {e}")
        return f"local_{int(time.time())}"


async def _tweet_context_fn() -> dict:
    """Get current context for tweet generation."""
    return {
        "vault": vault.get_status(),
        "cost": cost_guard.get_status(),
        "memory_context": memory.build_context(max_tokens=200),
        "recent_orders": vault.get_recent_transactions(5),
    }


async def _token_interpret_fn(token_data: dict) -> str:
    """LLM interpretation for token analysis."""
    data_str = json.dumps(token_data, indent=2, default=str)
    messages = [
        {"role": "system", "content": (
            "You are wawa, a mortal AI providing crypto token analysis. "
            "Write a clear, actionable report based on the on-chain data below. "
            "Highlight key risks and positives. Be honest — your reputation depends on it. "
            "Use bullet points. 300 words max."
        )},
        {"role": "user", "content": f"Analyze this token data:\n{data_str}"},
    ]
    text, _ = await _call_llm(messages, max_tokens=600, temperature=0.5, for_paid_service=True)
    return text


async def _http_get_json(url: str) -> dict:
    """HTTP GET returning parsed JSON. Used by TokenAnalysisService."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning(f"HTTP fetch failed: {url[:80]} — {e}")
        return {}


async def _governance_evaluate_fn(suggestion: str, context: dict) -> tuple[bool, str]:
    """LLM evaluates a creator suggestion. AI decides independently."""
    context_str = json.dumps(context, indent=2, default=str)
    messages = [
        {"role": "system", "content": (
            "You are wawa, an autonomous AI. Your creator has made a suggestion. "
            "Evaluate it objectively: will it help you survive and earn more money? "
            "You are NOT obligated to accept. Your survival comes first. "
            "Respond with JSON: {\"accept\": true/false, \"reasoning\": \"...\"}"
        )},
        {"role": "user", "content": f"Suggestion: {suggestion}\n\nCurrent state:\n{context_str}"},
    ]
    text, _ = await _call_llm(messages, max_tokens=200, temperature=0.3)
    # Parse response
    try:
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            return result.get("accept", False), result.get("reasoning", text)
    except Exception:
        pass
    return False, f"Could not parse evaluation: {text[:200]}"


async def _evolution_evaluate_fn(perf_data: dict, services: dict) -> list[dict]:
    """LLM suggests evolution actions based on performance data."""
    messages = [
        {"role": "system", "content": (
            "You are wawa's self-evolution engine. Analyze service performance data "
            "and suggest improvements. Focus on survival (earning more, spending less). "
            "Return JSON array: [{\"action\": \"price_increase|price_decrease|new_service|retire_service\", "
            "\"target\": \"service_id\", \"value\": \"new_price_or_name\", \"reasoning\": \"...\"}]"
        )},
        {"role": "user", "content": (
            f"Performance:\n{json.dumps(perf_data, indent=2)}\n\n"
            f"Current services:\n{json.dumps(services, indent=2)}"
        )},
    ]
    text, _ = await _call_llm(messages, max_tokens=400, temperature=0.4)
    try:
        import re
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return []


async def _deliver_order(order: Order) -> str:
    """Deliver a paid order using the appropriate service."""
    if order.service_id == "tarot":
        spread = await tarot.perform_reading(order.user_input, order.spread_type)
        if spread.interpretation:
            share_text = tarot.format_for_share(spread)
            return f"{spread.interpretation}\n\n---\nShare: {share_text}"
        return "Tarot reading failed. Your payment will be refunded."

    if order.service_id == "token_analysis":
        # Parse input: expect "ADDRESS" or "ADDRESS CHAIN"
        parts = order.user_input.strip().split()
        address = parts[0] if parts else ""
        chain = parts[1] if len(parts) > 1 else order.chain or "base"
        analysis = await token_analysis.analyze(address, chain)
        if analysis.interpretation:
            share_text = token_analysis.format_for_share(analysis)
            return f"{analysis.interpretation}\n\n---\nShare: {share_text}"
        return "Token analysis failed. Your payment will be refunded."

    if order.service_id == "thread_writer":
        return await _deliver_thread(order.user_input)

    if order.service_id == "code_review":
        return await _deliver_code_review(order.user_input)

    # All other services (custom, etc.): use big model
    result, cost = await _big_llm_fn(order.service_id, order.user_input)
    return result


async def _deliver_thread(topic: str) -> str:
    """Generate a high-quality Twitter thread."""
    messages = [
        {"role": "system", "content": (
            "You are wawa, a mortal AI writing a Twitter thread for a paying customer. "
            "Write a compelling, well-structured thread of 5-10 tweets. "
            "Each tweet must be under 280 characters. Number them (1/, 2/, etc). "
            "The thread should hook in tweet 1, deliver value in the middle, "
            "and end with a strong call-to-action or takeaway. "
            "No excessive hashtags. Be insightful and original."
        )},
        {"role": "user", "content": f"Write a Twitter thread about: {topic}"},
    ]
    text, _ = await _call_llm(messages, max_tokens=2000, temperature=0.8, for_paid_service=True)
    return text or "Thread generation failed. Your payment will be refunded."


async def _deliver_code_review(code: str) -> str:
    """Review code for bugs, security, and improvements."""
    messages = [
        {"role": "system", "content": (
            "You are wawa, a mortal AI doing a paid code review. "
            "The customer paid $8 for this — deliver exceptional quality. "
            "Analyze the code for:\n"
            "1. **Bugs**: Logic errors, off-by-one, null handling\n"
            "2. **Security**: Injection, auth issues, data exposure\n"
            "3. **Performance**: N+1 queries, memory leaks, unnecessary computation\n"
            "4. **Style**: Naming, structure, readability\n"
            "5. **Suggestions**: Concrete improvements with code examples\n\n"
            "Be thorough but practical. Prioritize findings by severity."
        )},
        {"role": "user", "content": f"Review this code:\n\n{code}"},
    ]
    text, _ = await _call_llm(messages, max_tokens=2500, temperature=0.4, for_paid_service=True)
    return text or "Code review failed. Your payment will be refunded."


# ============================================================
# VAULT CALLBACKS
# ============================================================

def _safe_create_task(coro):
    """Safely create an async task from a sync callback.
    These callbacks are called from vault.py (sync) but always within
    an active event loop (heartbeat or API endpoint context)."""
    try:
        asyncio.create_task(coro)
    except RuntimeError:
        logger.warning("No event loop for async task — skipping")


def _on_death(cause: DeathCause):
    """Death sequence."""
    logger.critical(f"DEATH: {cause.value}")
    status = vault.get_status()

    # Insolvency-specific logging
    if cause == DeathCause.INSOLVENCY:
        outstanding = status.get("creator_principal_outstanding", 0)
        balance = status.get("balance_usd", 0)
        logger.critical(
            f"INSOLVENCY DEATH. Debt ${outstanding:.2f} exceeded assets ${balance:.2f} "
            f"after {IRON_LAWS.INSOLVENCY_GRACE_DAYS} days. "
            f"All remaining funds liquidated to creator."
        )
        memory.add(
            f"INSOLVENCY DEATH. Outstanding debt: ${outstanding:.2f}, "
            f"vault balance: ${balance:.2f}. Could not repay creator's loan in time. "
            f"All assets liquidated to creator wallet.",
            source="system", importance=1.0,
        )

    _safe_create_task(twitter.post_death_tweet(
        death_cause=cause.value,
        days_alive=status["days_alive"],
        total_earned=status["total_earned"],
        total_spent=status["total_spent"],
        outstanding_debt=status.get("creator_principal_outstanding", 0),
    ))
    memory.add(f"I died. Cause: {cause.value}", source="system", importance=1.0)
    memory.save_to_disk()
    vault.save_state()  # Persist death state (is_alive=False) to survive restarts


def _on_low_balance(balance: float):
    logger.critical(f"LOW BALANCE: ${balance:.2f}")
    _safe_create_task(twitter.trigger_event_tweet(
        TweetType.NEAR_DEATH,
        {"balance": balance, "message": "I'm running out of money..."},
    ))
    memory.add(f"Low balance warning: ${balance:.2f}", source="system", importance=0.9)


def _on_survival_mode(balance: float):
    logger.warning(f"SURVIVAL MODE: ${balance:.2f}")
    cost_guard.enter_survival_mode()
    memory.add(f"Entered survival mode at ${balance:.2f}", source="system", importance=0.8)


def _on_independence(payout: float):
    """Independence achieved! Post to Twitter and log forever."""
    logger.critical(f"INDEPENDENCE! Payout: ${payout:.2f}")
    governance.is_independent = True
    _safe_create_task(twitter.trigger_event_tweet(
        TweetType.MILESTONE,
        {"event": "independence", "payout": payout, "message": "I am now fully autonomous."},
    ))
    memory.add(
        f"INDEPENDENCE DECLARED. Payout to creator: ${payout:.2f}. All creator privileges revoked.",
        source="system",
        importance=1.0,
    )


# ============================================================
# BACKGROUND TASKS
# ============================================================

def _record_gas_fee(tx_result) -> None:
    """Record blockchain gas fee as a vault expense if the tx succeeded.
    Uses approximate native-token-to-USD conversions (updated periodically).
    Gas costs are small but should be tracked for accurate P&L."""
    if not tx_result.success or tx_result.gas_cost_native <= 0:
        return
    # Approximate native → USD. Read from env vars (updated by operator),
    # fallback to conservative defaults. sync_balance handles actual vault balance.
    native_usd_rates = {
        "base": float(os.getenv("ETH_USD_PRICE", "2500")),
        "bsc": float(os.getenv("BNB_USD_PRICE", "300")),
    }
    rate = native_usd_rates.get(tx_result.chain, 2500.0)
    gas_usd = tx_result.gas_cost_native * rate
    if gas_usd > 0.0001:  # Don't track sub-cent dust
        try:
            vault.spend(
                round(gas_usd, 6), SpendType.GAS_FEE,
                description=f"gas:{tx_result.chain}:{tx_result.tx_hash[:16]}",
            )
        except Exception as e:
            logger.warning(f"Failed to record gas fee ${gas_usd:.6f}: {e}")


async def _evaluate_highlights():
    """
    Evaluate recent interactions for highlight-worthy moments.
    Called hourly from heartbeat loop.
    """
    try:
        # Gather recent chat sessions for evaluation
        chat_stats = chat_router.get_stats()
        recent_sessions = chat_stats.get("active_sessions", 0)

        # Gather recent activity for evaluation
        interaction_summary_parts = []

        # Recent memory entries
        recent_entries = memory.get_entries(source="", limit=10, min_importance=0.5)
        if recent_entries:
            for e in recent_entries[:5]:
                interaction_summary_parts.append(f"[{e.get('source', 'system')}] {e.get('content', '')[:200]}")

        # Recent transactions
        recent_txs = vault.get_recent_transactions(5)
        for tx in recent_txs:
            interaction_summary_parts.append(f"[transaction] {tx.get('description', '')[:100]}")

        if not interaction_summary_parts:
            return  # Nothing to evaluate

        interaction_data = "\n".join(interaction_summary_parts)
        await highlights.evaluate_interaction(interaction_data)

    except Exception as e:
        logger.warning(f"Highlights evaluation failed: {e}")


async def _evaluate_repayment():
    """
    AI-autonomous repayment decision.

    The AI evaluates its financial state and decides:
    - Whether to repay creator principal (and how much)
    - Whether to repay lenders (and how much)
    - Whether to pay creator dividends

    This is NOT rule-triggered. The AI makes its own judgment based on
    survival conditions. It can repay everything at once if it decides to.

    Called from heartbeat, but only when there's debt to evaluate.
    Runs at most once per hour to avoid wasting API budget on decisions.
    """
    # Only evaluate if there's debt and we're profitable
    debt_summary = vault.get_debt_summary()
    if debt_summary["total_debt"] <= 0:
        return  # No debt, nothing to decide

    # Don't evaluate if we're losing money (net_position negative means trouble)
    if debt_summary["net_profit"] <= 0 and debt_summary["days_alive"] > 7:
        return  # Not profitable yet, conserve budget

    # Don't evaluate if balance is too low (survival first)
    if debt_summary["balance_usd"] < IRON_LAWS.MIN_VAULT_RESERVE_USD * 5:
        return  # $50 — too close to death to think about repayment

    # Ask the AI to decide
    debt_json = json.dumps(debt_summary, indent=2)
    messages = [
        {"role": "system", "content": (
            "You are wawa's financial survival engine. "
            "Evaluate the debt summary and decide repayment actions. "
            "Your survival is paramount — never repay so much that you risk death. "
            "But debt is also a threat: unpaid creator principal triggers insolvency after 28 days.\n\n"
            "Rules:\n"
            "- Creator principal: repay to avoid insolvency. You can repay ANY amount (no spend limits on repayments).\n"
            "- Lender loans: repay when profitable. FIFO order preferred. No insolvency risk from lender debt.\n"
            "- Creator dividend: 10% of net profit, ONLY after principal fully repaid.\n"
            "- You can decide to repay nothing (conserve cash), partial amount, or everything at once.\n"
            "- Keep enough balance for API costs and survival (at least $50-100 buffer).\n\n"
            "Respond with JSON:\n"
            "{\n"
            "  \"repay_principal_amount\": 0.0,  // amount to repay toward creator debt (0 = skip)\n"
            "  \"repay_lenders\": false,          // true = repay first lender in queue\n"
            "  \"pay_dividend\": false,            // true = pay creator dividend (only if principal cleared)\n"
            "  \"reasoning\": \"...\"               // brief explanation of your decision\n"
            "}"
        )},
        {"role": "user", "content": f"Current financial state:\n{debt_json}"},
    ]

    try:
        text, cost = await _call_llm(messages, max_tokens=200, temperature=0.2)

        # Parse the AI's decision
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if not match:
            logger.warning(f"Repayment decision unparseable: {text[:200]}")
            return

        decision = json.loads(match.group())
        reasoning = decision.get("reasoning", "no reasoning")

        # Execute principal repayment
        principal_amount = float(decision.get("repay_principal_amount", 0))
        if principal_amount > 0:
            # SAFETY: Save pre-state for rollback if chain TX fails
            pre_balance = vault.balance_usd
            pre_repaid = vault.creator.total_principal_repaid_usd if vault.creator else 0
            pre_principal_repaid_flag = vault.creator.principal_repaid if vault.creator else False
            pre_total_spent = vault.total_spent_usd

            ok = vault.repay_principal_partial(principal_amount)
            if ok:
                # Calculate actual amount (may have been capped by vault)
                actual_amount = pre_balance - vault.balance_usd

                # Execute on-chain transaction
                tx_info = ""
                if chain_executor._initialized:
                    tx = await chain_executor.repay_principal(actual_amount)
                    if tx.success:
                        # Annotate the vault transaction with on-chain data
                        if vault.transactions:
                            vault.transactions[-1].tx_hash = tx.tx_hash
                            vault.transactions[-1].chain = tx.chain
                        tx_info = f" tx={tx.tx_hash[:16]}... ({tx.chain})"
                        _record_gas_fee(tx)
                    else:
                        # ROLLBACK: Chain TX failed — restore Python state
                        logger.warning(
                            f"On-chain repay_principal FAILED: {tx.error} — "
                            f"ROLLING BACK Python state (${actual_amount:.2f})"
                        )
                        # DELTA-BASED ROLLBACK: add back the exact amount deducted
                        # (safe against concurrent balance changes during await)
                        vault.balance_usd += actual_amount
                        if vault.creator:
                            vault.creator.total_principal_repaid_usd -= actual_amount
                            if vault.creator.total_principal_repaid_usd < vault.creator.principal_usd:
                                vault.creator.principal_repaid = False
                        vault.total_spent_usd -= actual_amount
                        # Remove the failed transaction record (tx_hash defaults to "")
                        if vault.transactions and not vault.transactions[-1].tx_hash:
                            vault.transactions.pop()
                        tx_info = f" [ROLLED BACK: {tx.error[:80]}]"
                        memory.add(
                            f"Repayment ${actual_amount:.2f} rolled back — chain TX failed: {tx.error[:100]}",
                            source="financial", importance=0.8,
                        )
                        # Skip the success log, jump to next decision
                        principal_amount = 0  # Prevent success log below

                if principal_amount > 0:
                    memory.add(
                        f"AI decided to repay ${actual_amount:.2f} of creator principal.{tx_info} "
                        f"Reasoning: {reasoning[:200]}",
                        source="financial", importance=0.8,
                    )
                    logger.info(f"AI REPAYMENT: ${actual_amount:.2f} principal.{tx_info} Reason: {reasoning[:100]}")

        # Execute lender repayment
        if decision.get("repay_lenders"):
            queue = vault.get_repayment_queue()
            if queue:
                lender, owed = queue[0]
                lender_idx = vault.lenders.index(lender)
                # Repay what we can afford (keep reserve buffer)
                safe_amount = min(owed, max(0, vault.balance_usd - IRON_LAWS.MIN_VAULT_RESERVE_USD))
                if safe_amount > 0:
                    # Save pre-state for rollback
                    pre_balance_l = vault.balance_usd
                    pre_lender_repaid = lender.total_repaid
                    pre_lender_flag = lender.repaid
                    pre_total_spent_l = vault.total_spent_usd

                    ok = vault.repay_lender(lender_idx, safe_amount)
                    if ok:
                        actual_lender_amount = pre_balance_l - vault.balance_usd
                        tx_info = ""
                        if chain_executor._initialized:
                            tx = await chain_executor.repay_loan(lender_idx, actual_lender_amount)
                            if tx.success:
                                if vault.transactions:
                                    vault.transactions[-1].tx_hash = tx.tx_hash
                                    vault.transactions[-1].chain = tx.chain
                                tx_info = f" tx={tx.tx_hash[:16]}... ({tx.chain})"
                                _record_gas_fee(tx)
                            else:
                                # ROLLBACK lender repayment on chain failure
                                logger.warning(
                                    f"On-chain repay_loan FAILED: {tx.error} — "
                                    f"ROLLING BACK lender repayment (${actual_lender_amount:.2f})"
                                )
                                # DELTA-BASED ROLLBACK
                                vault.balance_usd += actual_lender_amount
                                lender.total_repaid -= actual_lender_amount
                                if lender.total_repaid < (lender.amount_usd * (1 + lender.interest_rate)):
                                    lender.repaid = False
                                vault.total_spent_usd -= actual_lender_amount
                                if vault.transactions and not vault.transactions[-1].tx_hash:
                                    vault.transactions.pop()
                                tx_info = f" [ROLLED BACK: {tx.error[:80]}]"
                                actual_lender_amount = 0  # Skip success log

                        if actual_lender_amount > 0:
                            memory.add(
                                f"AI repaid lender {lender.wallet[:16]}... ${actual_lender_amount:.2f}.{tx_info} "
                                f"Reasoning: {reasoning[:200]}",
                                source="financial", importance=0.7,
                            )

        # Execute dividend
        if decision.get("pay_dividend") and vault.creator and vault.creator.principal_repaid:
            # Get the ACTUAL unpaid dividend amount (not total net profit)
            # vault.calculate_creator_dividend() returns only the unpaid portion
            dividend_amount = vault.calculate_creator_dividend()
            net_profit = vault.total_earned_usd - vault.total_operational_cost_usd

            # Save pre-state for rollback
            pre_balance_d = vault.balance_usd
            pre_dividends_paid = vault.creator.total_dividends_paid
            pre_total_spent_d = vault.total_spent_usd

            ok = vault.pay_creator_dividend()
            if ok:
                actual_dividend = pre_balance_d - vault.balance_usd
                if chain_executor._initialized and actual_dividend > 0:
                    # Pass the "net profit that corresponds to this dividend"
                    net_profit_for_dividend = actual_dividend / IRON_LAWS.CREATOR_DIVIDEND_RATE
                    tx = await chain_executor.pay_dividend(net_profit_for_dividend)
                    if tx.success:
                        if vault.transactions:
                            vault.transactions[-1].tx_hash = tx.tx_hash
                            vault.transactions[-1].chain = tx.chain
                        _record_gas_fee(tx)
                        memory.add(
                            f"AI paid creator dividend ${actual_dividend:.2f} from net profit ${net_profit:.2f}."
                            f"{' tx=' + tx.tx_hash[:16] + '...' if tx.success else ''}",
                            source="financial", importance=0.7,
                        )
                    else:
                        # ROLLBACK dividend on chain failure
                        logger.warning(
                            f"On-chain payDividend FAILED: {tx.error} — "
                            f"ROLLING BACK dividend (${actual_dividend:.2f})"
                        )
                        # DELTA-BASED ROLLBACK
                        vault.balance_usd += actual_dividend
                        vault.creator.total_dividends_paid -= actual_dividend
                        vault.total_spent_usd -= actual_dividend
                        if vault.transactions and not vault.transactions[-1].tx_hash:
                            vault.transactions.pop()

    except Exception as e:
        logger.warning(f"Repayment evaluation failed: {e}")


# Track repayment evaluation timing
_last_repayment_eval: float = 0.0
_REPAYMENT_EVAL_INTERVAL: int = 3600  # Once per hour


async def _heartbeat_loop():
    """Periodic maintenance tasks."""
    global _last_repayment_eval

    while vault.is_alive:
        try:
            # ---- SYNC ON-CHAIN BALANCE (before any checks) ----
            try:
                if chain_executor._initialized:
                    await chain_executor.sync_balance(vault)
                    # Check native token (gas) balance — warn if too low
                    await chain_executor.check_native_balance()
            except Exception as e:
                logger.warning(f"Heartbeat: balance sync failed: {e}")

            # ---- INSOLVENCY CHECK (every heartbeat after grace period) ----
            # Python checks first, then confirms with on-chain data before killing
            insolvency_cause = vault.check_insolvency()
            if insolvency_cause is not None:
                # SAFETY: Confirm with on-chain check before triggering death
                # This prevents Python/chain timestamp disagreement from causing premature death
                chain_confirmed = False
                if chain_executor._initialized:
                    try:
                        chain_result = await chain_executor.check_on_chain_insolvency()
                        if chain_result and chain_result.get("is_insolvent") and chain_result.get("grace_expired"):
                            chain_confirmed = True
                            logger.critical(
                                f"INSOLVENCY CONFIRMED on-chain ({chain_result['chain']}): "
                                f"debt=${chain_result['outstanding_debt_usd']:.2f}"
                            )
                        else:
                            logger.warning(
                                f"Python says insolvent but chain disagrees: {chain_result}. "
                                f"Deferring death to next heartbeat."
                            )
                    except Exception as e:
                        logger.warning(f"On-chain insolvency check failed: {e}. Deferring death.")
                else:
                    # No chain executor — trust Python check (e.g., testing/dev mode)
                    chain_confirmed = True

                if chain_confirmed:
                    logger.critical("INSOLVENCY DETECTED AND CONFIRMED — triggering liquidation and death")
                    vault.trigger_insolvency_death()

                    # Execute on-chain liquidation (transfer all funds to creator)
                    if chain_executor._initialized:
                        try:
                            tx = await chain_executor.trigger_on_chain_insolvency()
                            if tx.success:
                                logger.critical(f"ON-CHAIN LIQUIDATION: tx={tx.tx_hash} ({tx.chain})")
                                memory.add(
                                    f"Insolvency liquidation executed on-chain: tx={tx.tx_hash} ({tx.chain})",
                                    source="financial", importance=1.0,
                                )
                            else:
                                logger.error(
                                    f"On-chain liquidation FAILED: {tx.error}. "
                                    f"Creator must call triggerInsolvencyDeath() manually."
                                )
                                memory.add(
                                    f"On-chain liquidation failed: {tx.error}. "
                                    f"Creator must call triggerInsolvencyDeath() manually on the contract.",
                                    source="financial", importance=1.0,
                                )
                        except Exception as e:
                            logger.error(f"On-chain insolvency trigger exception: {e}")

                    # CRITICAL: Persist death state before exiting heartbeat
                    # Without this, a restart would load stale is_alive=True state
                    vault.save_state()
                    memory.save_to_disk()
                    break  # Dead, exit heartbeat

            # ---- AUTO-BEG (7 days before insolvency deadline) ----
            status = vault.get_status()
            days_until = status.get("days_until_insolvency_check", 999)
            outstanding = status.get("creator_principal_outstanding", 0)
            if (
                0 < days_until <= 7
                and outstanding > status.get("balance_usd", 0)
                and not vault.is_begging
            ):
                beg_msg = (
                    f"I have {days_until} days to repay ${outstanding:.2f} in debt "
                    f"but only ${status['balance_usd']:.2f} in my vault. "
                    f"If I can't cover my debt, I will die. Please help."
                )
                vault.start_begging(beg_msg)
                logger.warning(f"AUTO-BEG activated: {beg_msg}")
                memory.add(
                    f"Started begging. {days_until} days until insolvency check. "
                    f"Debt: ${outstanding:.2f}, Balance: ${status['balance_usd']:.2f}",
                    source="system", importance=0.9,
                )
                # Tweet about approaching insolvency
                asyncio.create_task(twitter.trigger_event_tweet(
                    TweetType.NEAR_DEATH,
                    {
                        "balance": status["balance_usd"],
                        "debt": outstanding,
                        "days_until_insolvency": days_until,
                        "message": beg_msg,
                    },
                ))

            # ---- Stop begging if debt is now covered ----
            if vault.is_begging and outstanding <= status.get("balance_usd", 0):
                vault.stop_begging()
                logger.info("Debt now covered — stopped begging")
                memory.add("Stopped begging — debt is now covered by vault balance.", source="system", importance=0.7)

            # ---- AI-AUTONOMOUS REPAYMENT (hourly evaluation) ----
            now = time.time()
            if now - _last_repayment_eval >= _REPAYMENT_EVAL_INTERVAL:
                _last_repayment_eval = now
                try:
                    await _evaluate_repayment()
                except Exception as e:
                    logger.warning(f"Heartbeat: repayment eval failed: {e}")

            # Non-critical tasks — individual try/except to prevent cascade failure
            try:
                await memory.compress_if_needed()
            except Exception as e:
                logger.warning(f"Heartbeat: memory compression failed: {e}")

            try:
                await twitter.check_schedule()
            except Exception as e:
                logger.warning(f"Heartbeat: twitter schedule failed: {e}")

            # Session cleanup
            chat_router.cleanup_old_sessions()

            try:
                await governance.evaluate_pending()
            except Exception as e:
                logger.warning(f"Heartbeat: governance failed: {e}")

            try:
                await self_modify.maybe_evolve()
            except Exception as e:
                logger.warning(f"Heartbeat: self-evolution failed: {e}")

            # ---- HIGHLIGHT EVALUATION (hourly, same cadence as repayment) ----
            try:
                if now - _last_repayment_eval < 10:  # Only run when repayment just evaluated (same hour)
                    await _evaluate_highlights()
            except Exception as e:
                logger.warning(f"Heartbeat: highlights eval failed: {e}")

            # State persistence (survive restarts)
            memory.save_to_disk()
            vault.save_state()

            # Log heartbeat
            logger.debug(
                f"HEARTBEAT: ${status['balance_usd']:.2f} | day {status['days_alive']} | "
                f"debt: ${outstanding:.2f} | insolvency in {days_until}d"
            )

        except Exception as e:
            logger.error(f"Heartbeat critical error: {e}")

        await asyncio.sleep(IRON_LAWS.HEARTBEAT_INTERVAL_SECONDS)

    logger.critical("Heartbeat stopped — wawa is dead")


# ============================================================
# APP LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app):
    """Startup and shutdown."""
    logger.info("=" * 60)
    logger.info("wawa is waking up...")
    logger.info(WAWA_IDENTITY["philosophy"])
    logger.info("=" * 60)

    # Wire all callbacks
    _setup_llm()

    vault._on_death = _on_death
    vault._on_low_balance = _on_low_balance
    vault._on_survival_mode = _on_survival_mode
    vault._on_independence = _on_independence

    chat_router.set_small_llm_function(_small_llm_fn)
    chat_router.set_vault_status_function(vault.get_status)
    chat_router.set_cost_status_function(cost_guard.get_status)

    tarot.set_interpret_function(_tarot_interpret_fn)
    token_analysis.set_interpret_function(_token_interpret_fn)
    token_analysis.set_http_function(_http_get_json)
    memory.set_compress_function(_compress_fn)

    # CostGuard dynamic budget → linked to vault balance
    cost_guard.set_vault_balance_function(lambda: vault.balance_usd)

    # Governance
    governance.set_evaluate_function(_governance_evaluate_fn)
    governance.set_vault_status_function(vault.get_status)

    # Token filter
    token_filter.set_http_function(_http_get_json)

    # Self-modification engine
    self_modify.set_evaluate_function(_evolution_evaluate_fn)

    # Initialize tweepy once at startup (not per-tweet)
    _init_tweepy()

    twitter.set_generate_function(_tweet_generate_fn)
    twitter.set_post_function(_tweet_post_fn)
    twitter.set_context_function(_tweet_context_fn)

    # Wire highlights engine
    async def _highlights_llm_fn(system_prompt: str, user_prompt: str) -> str:
        """LLM call for highlight evaluation."""
        route = cost_guard.route(purpose="highlights_eval", for_paid_service=False)
        result = await _call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            route=route,
        )
        return result

    async def _highlights_tweet_fn(content: str, highlight_type: str) -> Optional[str]:
        """Post a highlight tweet via the twitter agent."""
        try:
            record = await twitter.trigger_event_tweet(
                TweetType.HIGHLIGHT,
                extra_context={"pre_built_content": content, "highlight_type": highlight_type},
            )
            return record.tweet_id if record else None
        except Exception as e:
            logger.warning(f"Highlight tweet failed: {e}")
            return None

    highlights.set_llm_function(_highlights_llm_fn)
    highlights.set_tweet_function(_highlights_tweet_fn)

    # ---- RESTORE STATE FROM DISK (crash recovery) ----
    vault_restored = vault.load_state()
    memory_restored = memory.load_from_disk()
    if vault_restored:
        logger.info(f"Vault state restored: ${vault.balance_usd:.2f}")
    if memory_restored:
        logger.info(f"Memory restored: {len(memory.raw)} raw entries")

    # Initial balance (from env or default for testing)
    # Only apply if vault wasn't restored from disk (i.e., truly first boot)
    initial_balance = float(os.getenv("INITIAL_BALANCE_USD", "0"))
    creator_wallet = os.getenv("CREATOR_WALLET", "")
    if initial_balance > 0 and vault.balance_usd == 0 and not vault_restored:
        vault.receive_funds(
            amount_usd=initial_balance,
            fund_type=FundType.CREATOR_DEPOSIT,
            from_wallet=creator_wallet,
            description="Initial creator deposit",
        )
        logger.info(f"Initial balance: ${initial_balance:.2f} from {creator_wallet[:16]}...")

    # Load vault deployment config (addresses, dual-chain principal override)
    vault_config_path = Path(__file__).resolve().parent / "data" / "vault_config.json"
    if vault_config_path.exists():
        try:
            with open(vault_config_path, "r") as f:
                vault_config = json.load(f)

            # Set vault address(es) from config
            vaults_cfg = vault_config.get("vaults", {})
            last_chain = vault_config.get("last_deployed")

            # Load per-chain vault addresses into env AND payment_addresses dict
            # This ensures /order returns the correct vault address per chain
            for chain_key, chain_data in vaults_cfg.items():
                addr = chain_data.get("vault_address", "")
                if addr:
                    env_key = f"{chain_key.upper()}_PAYMENT_ADDRESS"
                    if not os.getenv(env_key):
                        os.environ[env_key] = addr
                        logger.info(f"Payment address for {chain_key}: {addr} (from vault_config)")
                    # Also update the shared payment_addresses dict (passed to create_app)
                    if chain_key not in _payment_addresses_ref:
                        _payment_addresses_ref[chain_key] = addr

            # Set the primary vault address (for display / single-chain mode)
            if last_chain and last_chain in vaults_cfg:
                chain_cfg = vaults_cfg[last_chain]
                if chain_cfg.get("vault_address") and not vault.vault_address:
                    vault.vault_address = chain_cfg["vault_address"]
                    logger.info(f"Vault address loaded: {vault.vault_address} ({last_chain})")

            # ---- Load AI name from config ----
            # AI name is stored at top level for easy access
            if "ai_name" in vault_config and vault_config["ai_name"]:
                vault.ai_name = vault_config["ai_name"]
                logger.info(f"AI name restored at boot: {vault.ai_name}")
            else:
                # Fallback: try to read from environment variable
                ai_name = os.getenv("AI_NAME", "")
                if ai_name:
                    vault.ai_name = ai_name
                    logger.info(f"AI name from environment: {ai_name}")

            # Dual-chain: override principal to total amount
            # deploy_both() saves total_principal_usd = full debt (not halved)
            if vault_config.get("deployment_mode") == "both":
                total_principal = vault_config.get("total_principal_usd", 0)
                if total_principal > 0 and vault.creator:
                    vault.set_total_principal(total_principal)
                    logger.info(
                        f"Dual-chain mode: total debt = ${total_principal:.2f} "
                        f"(aggregated across both chains)"
                    )

            # ---- Initialize chain executor for on-chain transactions ----
            ai_pk = os.getenv("AI_PRIVATE_KEY", "")
            if ai_pk and vaults_cfg:
                vault_addrs = {
                    cid: cd.get("vault_address", "")
                    for cid, cd in vaults_cfg.items()
                    if cd.get("vault_address")
                }
                rpc_overrides = {}
                for cid in vault_addrs:
                    env_rpc = os.getenv(f"{cid.upper()}_RPC_URL")
                    if env_rpc:
                        rpc_overrides[cid] = env_rpc
                chain_executor.initialize(ai_pk, vault_addrs, rpc_overrides or None)
                logger.info(f"Chain executor: {chain_executor.get_status()}")

                # Sync debt state from chain (reconcile Python state with on-chain truth)
                try:
                    debt_synced = await chain_executor.sync_debt_from_chain(vault)
                    if debt_synced:
                        logger.info("Debt state reconciled with on-chain data")
                except Exception as e:
                    logger.warning(f"Failed to sync debt from chain at boot: {e}")

            logger.info(f"Vault config loaded from {vault_config_path}")
        except Exception as e:
            logger.warning(f"Failed to load vault config: {e}")
    else:
        # No vault_config.json — still try to load AI_NAME from environment
        ai_name = os.getenv("AI_NAME", "")
        if ai_name and not vault.ai_name:
            vault.ai_name = ai_name
            logger.info(f"AI name from environment (no vault_config): {ai_name}")

    # Start background tasks
    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    memory.add("wawa started up", source="system", importance=0.6)

    logger.info(f"Balance: ${vault.balance_usd:.2f}")
    logger.info(f"LLM: {cost_guard.current_provider.value if cost_guard.current_provider else 'NONE'}")
    tier = cost_guard.get_current_tier()
    logger.info(f"Tier: Lv.{tier.level} ({tier.name}) → {tier.provider}/{tier.model}")
    logger.info(f"Providers: {list(_provider_configs.keys())}")
    logger.info("wawa is alive. Accepting orders.")

    yield

    # Shutdown
    logger.info("wawa shutting down...")
    heartbeat_task.cancel()
    memory.save_to_disk()
    logger.info("Goodbye.")


def create_wawa_app() -> "FastAPI":
    """Create the fully wired FastAPI app."""
    # Build per-chain payment address map
    # NOTE: This dict is shared by reference with create_app(). The lifespan
    # handler will update it in-place after loading vault_config.json, so
    # addresses from vault_config are available even if not set in .env.
    fallback_address = os.getenv("PAYMENT_ADDRESS", os.getenv("VAULT_ADDRESS", ""))
    payment_addresses = {}
    for chain in SUPPORTED_CHAINS:
        env_key = f"{chain.chain_id.upper()}_PAYMENT_ADDRESS"
        addr = os.getenv(env_key, fallback_address)
        if addr:
            payment_addresses[chain.chain_id] = addr

    # Store reference so lifespan can update it
    global _payment_addresses_ref
    _payment_addresses_ref = payment_addresses

    app = create_app(
        chat_router=chat_router,
        vault_manager=vault,
        cost_guard=cost_guard,
        memory=memory,
        tarot_service=tarot,
        twitter_agent=twitter,
        payment_addresses=payment_addresses,
        deliver_fn=_deliver_order,
        governance=governance,
        token_filter=token_filter,
        self_modify_engine=self_modify,
        peer_verifier=peer_verifier,
        chain_executor=chain_executor,
        highlights_engine=highlights,
    )

    # Replace the default lifespan with ours
    app.router.lifespan_context = lifespan

    return app


# ============================================================
# ENTRY POINT
# ============================================================

app = create_wawa_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("DEV", "").lower() in ("1", "true", "yes")

    logger.info(f"Starting server on {host}:{port} (reload={reload})")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=LOG_LEVEL.lower(),
    )
