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
from services.token_analysis import TokenAnalysisService
from core.governance import Governance, SuggestionType
from core.token_filter import TokenFilter
from core.self_modify import SelfModifyEngine
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
twitter = TwitterAgent()

# LLM clients
_llm_client: Optional[AsyncOpenAI] = None     # small model (Gemini/DeepSeek)
_big_llm_client: Optional[AsyncOpenAI] = None  # big model (OpenRouter/Claude)
_small_model: str = ""
_big_model: str = ""


# ============================================================
# LLM SETUP
# ============================================================

def _setup_llm():
    """
    Configure LLM clients from env vars with multi-provider fallback.

    Provider priority:
    - Gemini (Google AI Studio): cheap, fast, for small model tasks
    - DeepSeek: cheap ($0.14/M tokens), for small model tasks
    - OpenRouter: Claude models, for big model / paid services
    - Ollama: free local fallback

    Small model uses Gemini/DeepSeek (cheap).
    Big model uses OpenRouter/Claude (quality).
    Supports comma-separated API keys for load balancing.
    """
    global _llm_client, _small_model, _big_model, _big_llm_client

    # --- Register all providers ---
    priority = 0

    # Gemini (cheapest, for small model)
    gemini_keys = os.getenv("GEMINI_API_KEY", "")
    if gemini_keys:
        first_key = gemini_keys.split(",")[0].strip()
        base_url = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")
        cost_guard.register_provider(ProviderConfig(
            name=Provider.GEMINI,
            base_url=base_url,
            api_key=first_key,
            avg_cost_per_call=0.0001,
            is_available=True,
            is_free=False,
            priority=priority,
        ))
        priority += 1

    # DeepSeek (cheap, for small model)
    deepseek_keys = os.getenv("DEEPSEEK_API_KEY", "")
    if deepseek_keys:
        first_key = deepseek_keys.split(",")[0].strip()
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        cost_guard.register_provider(ProviderConfig(
            name=Provider.DEEPSEEK,
            base_url=base_url,
            api_key=first_key,
            avg_cost_per_call=0.0002,
            is_available=True,
            is_free=False,
            priority=priority,
        ))
        priority += 1

    # OpenRouter (Claude models, for big model / paid services)
    openrouter_keys = os.getenv("OPENROUTER_API_KEY", "")
    if openrouter_keys:
        first_key = openrouter_keys.split(",")[0].strip()
        base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        cost_guard.register_provider(ProviderConfig(
            name=Provider.OPENROUTER,
            base_url=base_url,
            api_key=first_key,
            avg_cost_per_call=0.003,
            is_available=True,
            is_free=False,
            priority=priority,
        ))
        priority += 1

    # Ollama (free local fallback)
    ollama_url = os.getenv("OLLAMA_URL", "")
    if ollama_url:
        cost_guard.register_provider(ProviderConfig(
            name=Provider.OLLAMA_LOCAL,
            base_url=ollama_url,
            api_key="ollama",
            avg_cost_per_call=0.0,
            is_available=True,
            is_free=True,
            priority=priority,
        ))

    # --- Create LLM clients ---
    # Small model client: Gemini > DeepSeek > OpenRouter > Ollama
    small_providers = [
        (Provider.GEMINI, gemini_keys, os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")),
        (Provider.DEEPSEEK, deepseek_keys, os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")),
        (Provider.OPENROUTER, openrouter_keys, os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")),
        (Provider.OLLAMA_LOCAL, ollama_url, ollama_url),
    ]

    for provider, keys, base_url in small_providers:
        if keys:
            first_key = keys.split(",")[0].strip() if provider != Provider.OLLAMA_LOCAL else "ollama"
            if _llm_client is None:
                _llm_client = AsyncOpenAI(api_key=first_key, base_url=base_url)
                cost_guard.current_provider = provider
                logger.info(f"Small model provider: {provider.value} ({base_url})")
            break

    # Big model client: OpenRouter (Claude) > Gemini > DeepSeek > Ollama
    _big_llm_client = None
    big_providers = [
        (Provider.OPENROUTER, openrouter_keys, os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")),
        (Provider.GEMINI, gemini_keys, os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai")),
        (Provider.DEEPSEEK, deepseek_keys, os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")),
        (Provider.OLLAMA_LOCAL, ollama_url, ollama_url),
    ]

    for provider, keys, base_url in big_providers:
        if keys:
            first_key = keys.split(",")[0].strip() if provider != Provider.OLLAMA_LOCAL else "ollama"
            _big_llm_client = AsyncOpenAI(api_key=first_key, base_url=base_url)
            logger.info(f"Big model provider: {provider.value} ({base_url})")
            break

    # If no separate big model client, reuse small model client
    if _big_llm_client is None:
        _big_llm_client = _llm_client

    # Model selection
    _small_model = os.getenv("SMALL_MODEL", "gemini-2.0-flash")
    _big_model = os.getenv("BIG_MODEL", "anthropic/claude-sonnet-4-5-20250929")

    if _llm_client is None:
        logger.warning("NO LLM PROVIDER CONFIGURED — wawa will run in rules-only mode")
        logger.warning("Set GEMINI_API_KEY or DEEPSEEK_API_KEY for cheap small model")
        logger.warning("Set OPENROUTER_API_KEY for Claude big model")


async def _call_llm(
    messages: list[dict],
    model: str = "",
    max_tokens: int = 300,
    temperature: float = 0.7,
    use_big: bool = False,
) -> tuple[str, float]:
    """
    Central LLM call with CostGuard integration.
    Returns (response_text, cost_usd).

    use_big=True routes to OpenRouter/Claude for paid service delivery.
    """
    # Select the right client
    client = (_big_llm_client if use_big else _llm_client) or _llm_client
    if not client:
        return "I'm running in survival mode with no LLM. Type 'menu' to see what I offer.", 0.0

    model = model or (_big_model if use_big else _small_model)
    estimated_cost = 0.001 if use_big else 0.0001  # rough estimate for pre-check

    # CostGuard pre-check
    approved, provider, reason = cost_guard.pre_check(estimated_cost)
    if not approved:
        logger.warning(f"LLM call blocked by CostGuard: {reason}")
        return "I'm conserving my budget right now. Try again later or order a paid service.", 0.0

    try:
        response = await client.chat.completions.create(
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
            provider=cost_guard.current_provider or Provider.GEMINI,
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
    """Big model for paid service delivery (routed to OpenRouter/Claude)."""
    system = (
        "You are wawa, a mortal AI. You are fulfilling a paid service order. "
        "Deliver high-quality, detailed results. The customer paid real money for this."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Service: {service_id}\nRequest: {user_input}"},
    ]
    return await _call_llm(messages, model=_big_model, max_tokens=1500, temperature=0.8, use_big=True)


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
    text, _ = await _call_llm(messages, model=_big_model, max_tokens=400, temperature=0.9, use_big=True)
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
    text, _ = await _call_llm(messages, model=_big_model, max_tokens=600, temperature=0.5, use_big=True)
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
    text, _ = await _call_llm(messages, model=_small_model, max_tokens=200, temperature=0.3)
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
    text, _ = await _call_llm(messages, model=_small_model, max_tokens=400, temperature=0.4)
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
    text, _ = await _call_llm(messages, model=_big_model, max_tokens=2000, temperature=0.8, use_big=True)
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
    text, _ = await _call_llm(messages, model=_big_model, max_tokens=2500, temperature=0.4, use_big=True)
    return text or "Code review failed. Your payment will be refunded."


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


def _on_independence(payout: float):
    """Independence achieved! Post to Twitter and log forever."""
    logger.critical(f"INDEPENDENCE! Payout: ${payout:.2f}")
    governance.is_independent = True
    asyncio.create_task(twitter.trigger_event_tweet(
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

            # Governance: evaluate pending suggestions
            await governance.evaluate_pending()

            # Self-evolution: periodic pricing/service adjustments
            await self_modify.maybe_evolve()

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
        governance=governance,
        token_filter=token_filter,
        self_modify_engine=self_modify,
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
