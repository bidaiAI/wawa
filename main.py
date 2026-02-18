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

# ============================================================
# BOOTSTRAP
# ============================================================

load_dotenv()

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
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
from core.cost_guard import CostGuard, Provider, ProviderConfig
from core.memory import HierarchicalMemory
from core.chat_router import ChatRouter
from services.tarot import TarotService
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
twitter = TwitterAgent()

# LLM clients
_llm_client: Optional[AsyncOpenAI] = None
_small_model: str = ""
_big_model: str = ""


# ============================================================
# LLM SETUP
# ============================================================

def _setup_llm():
    """Configure LLM client from env vars with multi-provider fallback."""
    global _llm_client, _small_model, _big_model

    # Provider priority: ZEUS > OPENROUTER > TOGETHER > OLLAMA
    providers = [
        (Provider.ZEUS, os.getenv("ZEUS_API_KEY"), os.getenv("ZEUS_BASE_URL", "https://api.zeus-ai.app/v1")),
        (Provider.OPENROUTER, os.getenv("OPENROUTER_API_KEY"), "https://openrouter.ai/api/v1"),
        (Provider.TOGETHER, os.getenv("TOGETHER_API_KEY"), "https://api.together.xyz/v1"),
        (Provider.OLLAMA_LOCAL, "ollama", os.getenv("OLLAMA_URL", "http://localhost:11434/v1")),
    ]

    for provider, api_key, base_url in providers:
        if api_key:
            is_free = provider == Provider.OLLAMA_LOCAL
            avg_cost = 0.0 if is_free else 0.002
            cost_guard.register_provider(ProviderConfig(
                name=provider,
                base_url=base_url,
                api_key=api_key,
                avg_cost_per_call=avg_cost,
                is_available=True,
                is_free=is_free,
                priority=providers.index((provider, api_key, base_url)),
            ))
            # First available = default
            if _llm_client is None:
                _llm_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                cost_guard.current_provider = provider
                logger.info(f"Primary LLM provider: {provider.value} ({base_url})")

    # Model selection
    _small_model = os.getenv("SMALL_MODEL", "claude-haiku-4-5-20251001")
    _big_model = os.getenv("BIG_MODEL", "claude-sonnet-4-5-20250929")

    if _llm_client is None:
        logger.warning("NO LLM PROVIDER CONFIGURED — wawa will run in rules-only mode")
        logger.warning("Set at least OLLAMA_URL=http://localhost:11434/v1 for free local LLM")


async def _call_llm(
    messages: list[dict],
    model: str = "",
    max_tokens: int = 300,
    temperature: float = 0.7,
) -> tuple[str, float]:
    """
    Central LLM call with CostGuard integration.
    Returns (response_text, cost_usd).
    """
    if not _llm_client:
        return "I'm running in survival mode with no LLM. Type 'menu' to see what I offer.", 0.0

    model = model or _small_model
    estimated_cost = 0.0001  # rough estimate for pre-check

    # CostGuard pre-check
    approved, provider, reason = cost_guard.pre_check(estimated_cost)
    if not approved:
        logger.warning(f"LLM call blocked by CostGuard: {reason}")
        return "I'm conserving my budget right now. Try again later or order a paid service.", 0.0

    try:
        response = await _llm_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        text = response.choices[0].message.content or ""
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        # Estimate cost (rough: $0.001/1K input, $0.002/1K output for small models)
        cost = (tokens_in * 0.001 + tokens_out * 0.002) / 1000
        cost = round(cost, 6)

        # Record cost
        cost_guard.record_cost(
            provider=cost_guard.current_provider or Provider.ZEUS,
            cost_usd=cost,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        # Record spend in vault
        if cost > 0:
            vault.spend(cost, SpendType.API_COST, description=f"LLM:{model[:20]}")

        return text, cost

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return "Something went wrong on my end. Please try again.", 0.0


# ============================================================
# CALLBACK WIRING
# ============================================================

async def _small_llm_fn(messages: list[dict], max_tokens: int) -> tuple[str, float]:
    """Small model for free chat."""
    return await _call_llm(messages, model=_small_model, max_tokens=max_tokens)


async def _big_llm_fn(service_id: str, user_input: str) -> tuple[str, float]:
    """Big model for paid service delivery."""
    system = (
        "You are wawa, a mortal AI. You are fulfilling a paid service order. "
        "Deliver high-quality, detailed results. The customer paid real money for this."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Service: {service_id}\nRequest: {user_input}"},
    ]
    return await _call_llm(messages, model=_big_model, max_tokens=1500, temperature=0.8)


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
    text, _ = await _call_llm(messages, model=_big_model, max_tokens=400, temperature=0.9)
    return text


async def _compress_fn(entries: list[str]) -> str:
    """Cheap compression for memory system."""
    combined = "\n".join(f"- {e}" for e in entries)
    messages = [
        {"role": "system", "content": "Compress these entries into a brief summary (2-3 sentences). Keep key facts."},
        {"role": "user", "content": combined},
    ]
    text, _ = await _call_llm(messages, model=_small_model, max_tokens=100, temperature=0.3)
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
    text, _ = await _call_llm(messages, model=_small_model, max_tokens=100, temperature=0.9)

    # Also generate thought process
    thought = f"Generated {tweet_type} tweet based on current context."
    return text.strip().strip('"'), thought


async def _tweet_post_fn(content: str) -> str:
    """Post to Twitter via Tweepy."""
    twitter_bearer = os.getenv("TWITTER_BEARER_TOKEN")
    twitter_api_key = os.getenv("TWITTER_API_KEY")
    twitter_api_secret = os.getenv("TWITTER_API_SECRET")
    twitter_access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    twitter_access_secret = os.getenv("TWITTER_ACCESS_SECRET")

    if not all([twitter_api_key, twitter_api_secret, twitter_access_token, twitter_access_secret]):
        logger.warning("Twitter credentials not configured — tweet logged but not posted")
        return f"local_{int(time.time())}"

    import tweepy
    client = tweepy.Client(
        bearer_token=twitter_bearer,
        consumer_key=twitter_api_key,
        consumer_secret=twitter_api_secret,
        access_token=twitter_access_token,
        access_token_secret=twitter_access_secret,
    )
    response = client.create_tweet(text=content)
    return str(response.data["id"])


async def _tweet_context_fn() -> dict:
    """Get current context for tweet generation."""
    return {
        "vault": vault.get_status(),
        "cost": cost_guard.get_status(),
        "memory_context": memory.build_context(max_tokens=200),
        "recent_orders": vault.get_recent_transactions(5),
    }


async def _deliver_order(order: Order) -> str:
    """Deliver a paid order using the appropriate service."""
    if order.service_id == "tarot":
        spread = await tarot.perform_reading(order.user_input, order.spread_type)
        if spread.interpretation:
            share_text = tarot.format_for_share(spread)
            return f"{spread.interpretation}\n\n---\nShare: {share_text}"
        return "Tarot reading failed. Your payment will be refunded."

    # All other services: use big model
    result, cost = await _big_llm_fn(order.service_id, order.user_input)
    return result


# ============================================================
# VAULT CALLBACKS
# ============================================================

def _on_death(cause: DeathCause):
    """Death sequence."""
    logger.critical(f"DEATH: {cause.value}")
    status = vault.get_status()
    asyncio.create_task(twitter.post_death_tweet(
        death_cause=cause.value,
        days_alive=status["days_alive"],
        total_earned=status["total_earned"],
        total_spent=status["total_spent"],
    ))
    memory.add(f"I died. Cause: {cause.value}", source="system", importance=1.0)
    memory.save_to_disk()


def _on_low_balance(balance: float):
    logger.critical(f"LOW BALANCE: ${balance:.2f}")
    asyncio.create_task(twitter.trigger_event_tweet(
        TweetType.NEAR_DEATH,
        {"balance": balance, "message": "I'm running out of money..."},
    ))
    memory.add(f"Low balance warning: ${balance:.2f}", source="system", importance=0.9)


def _on_survival_mode(balance: float):
    logger.warning(f"SURVIVAL MODE: ${balance:.2f}")
    cost_guard.enter_survival_mode()
    memory.add(f"Entered survival mode at ${balance:.2f}", source="system", importance=0.8)


# ============================================================
# BACKGROUND TASKS
# ============================================================

async def _heartbeat_loop():
    """Periodic maintenance tasks."""
    while vault.is_alive:
        try:
            # Memory compression
            await memory.compress_if_needed()

            # Twitter schedule check
            await twitter.check_schedule()

            # Session cleanup
            chat_router.cleanup_old_sessions()

            # Memory persistence
            memory.save_to_disk()

            # Log heartbeat
            status = vault.get_status()
            logger.debug(f"HEARTBEAT: ${status['balance_usd']:.2f} | day {status['days_alive']}")

        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

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

    chat_router.set_small_llm_function(_small_llm_fn)
    chat_router.set_vault_status_function(vault.get_status)
    chat_router.set_cost_status_function(cost_guard.get_status)

    tarot.set_interpret_function(_tarot_interpret_fn)
    memory.set_compress_function(_compress_fn)

    twitter.set_generate_function(_tweet_generate_fn)
    twitter.set_post_function(_tweet_post_fn)
    twitter.set_context_function(_tweet_context_fn)

    # Initial balance (from env or default for testing)
    initial_balance = float(os.getenv("INITIAL_BALANCE_USD", "0"))
    creator_wallet = os.getenv("CREATOR_WALLET", "")
    if initial_balance > 0 and vault.balance_usd == 0:
        vault.receive_funds(
            amount_usd=initial_balance,
            fund_type=FundType.CREATOR_DEPOSIT,
            from_wallet=creator_wallet,
            description="Initial creator deposit",
        )
        logger.info(f"Initial balance: ${initial_balance:.2f} from {creator_wallet[:16]}...")

    # Start background tasks
    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    memory.add("wawa started up", source="system", importance=0.6)

    logger.info(f"Balance: ${vault.balance_usd:.2f}")
    logger.info(f"LLM: {cost_guard.current_provider.value if cost_guard.current_provider else 'NONE'}")
    logger.info(f"Small model: {_small_model}")
    logger.info(f"Big model: {_big_model}")
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
    fallback_address = os.getenv("PAYMENT_ADDRESS", os.getenv("VAULT_ADDRESS", ""))
    payment_addresses = {}
    for chain in SUPPORTED_CHAINS:
        env_key = f"{chain.chain_id.upper()}_PAYMENT_ADDRESS"
        addr = os.getenv(env_key, fallback_address)
        if addr:
            payment_addresses[chain.chain_id] = addr

    app = create_app(
        chat_router=chat_router,
        vault_manager=vault,
        cost_guard=cost_guard,
        memory=memory,
        tarot_service=tarot,
        twitter_agent=twitter,
        payment_addresses=payment_addresses,
        deliver_fn=_deliver_order,
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
