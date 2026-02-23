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


class _SecretMaskingFilter(logging.Filter):
    """Redact 64-char hex strings (private keys) from all log output."""
    import re as _re
    _PATTERN = _re.compile(r'(?<![0-9a-fA-F])([0-9a-fA-F]{64})(?![0-9a-fA-F])')

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        if isinstance(record.msg, str):
            record.msg = self._PATTERN.sub('[REDACTED]', record.msg)
        if record.args:
            try:
                formatted = record.getMessage()
                if self._PATTERN.search(formatted):
                    record.msg = self._PATTERN.sub('[REDACTED]', formatted)
                    record.args = None
            except Exception:
                pass
        return True


_mask_filter = _SecretMaskingFilter()
for _h in logging.root.handlers:
    _h.addFilter(_mask_filter)

logger = logging.getLogger("mortal.main")

# Ensure data dirs exist
for d in ["data/memory", "data/tweets", "data/orders", "data/takeover", "data/takeover_reports"]:
    Path(d).mkdir(parents=True, exist_ok=True)


# ============================================================
# MODULE IMPORTS
# ============================================================

from core.constitution import IRON_LAWS, WAWA_IDENTITY, DeathCause, SUPPORTED_CHAINS, DEFAULT_CHAIN, MODEL_TIERS
from core.vault import VaultManager, FundType, SpendType
from core.cost_guard import CostGuard, Provider, ProviderConfig, RoutingResult, PROVIDER_MAP
from core.memory import HierarchicalMemory
from core.chat_router import ChatRouter
from services.tarot import TarotService
from services.token_analysis import TokenAnalysisService
from services._registry import ServiceRegistry
from services.giveaway import GiveawayEngine
from core.governance import Governance, SuggestionType
from core.token_filter import TokenFilter
from core.self_modify import SelfModifyEngine
from core.chain import ChainExecutor
from core.peer_verifier import PeerVerifier
import core.xai_search as xai_search
from core.highlights import HighlightsEngine
from core.purchasing import PurchaseManager, MerchantRegistry
from twitter.agent import TwitterAgent, TweetType, TweetRecord
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
service_registry = ServiceRegistry()   # Dynamic plugin loader for AI-created services
governance = Governance()
token_filter = TokenFilter()
self_modify = SelfModifyEngine()
chain_executor = ChainExecutor()
peer_verifier = PeerVerifier()
highlights = HighlightsEngine()
twitter = TwitterAgent()
giveaway_engine = GiveawayEngine()

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

    # xAI Search (on-demand Twitter/X context injection — NOT a tier provider)
    xai_key = os.getenv("XAI_API_KEY", "")
    xai_base = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
    if xai_search.initialize(xai_key, xai_base):
        logger.info("xAI Search: X Search + Web Search enabled (on-demand injection)")

    # xAI/Grok for high-quality Twitter replies (richer=smarter principle)
    _setup_xai_twitter()

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


# ============================================================
# xAI / GROK — High-Quality Twitter Reply Engine
# ============================================================
# When the AI is rich enough, Twitter replies use Grok for best quality.
# "Richer = smarter" — the AI's public voice improves with wealth.
# xAI API is OpenAI-compatible (https://api.x.ai/v1)

_xai_client: Optional[AsyncOpenAI] = None
_XAI_MODEL = os.getenv("XAI_TWITTER_MODEL", "grok-3-mini")


def _setup_xai_twitter():
    """Initialize xAI client for high-quality Twitter replies."""
    global _xai_client
    xai_key = os.getenv("XAI_API_KEY", "")
    if not xai_key:
        return
    xai_base = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
    _xai_client = AsyncOpenAI(api_key=xai_key, base_url=xai_base, timeout=30.0)
    logger.info(f"xAI Twitter reply engine: {_XAI_MODEL} enabled (high-quality replies)")


async def _call_xai(
    messages: list[dict],
    max_tokens: int = 200,
    temperature: float = 0.85,
) -> tuple[str, float]:
    """
    Call xAI/Grok for high-quality Twitter reply generation.

    Falls back to normal _call_llm if xAI is not configured.
    Cost is tracked through CostGuard for platform fee settlement.
    """
    if not _xai_client:
        return await _call_llm(messages, max_tokens=max_tokens, temperature=temperature, for_paid_service=True)

    try:
        response = await _xai_client.chat.completions.create(
            model=_XAI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = response.choices[0].message.content or ""
        usage = response.usage
        cost = 0.0
        if usage:
            # grok-3-mini: ~$0.30/1M input, $0.50/1M output
            cost = (usage.prompt_tokens * 0.30 + usage.completion_tokens * 0.50) / 1_000_000
        # Record cost (xAI cost goes through same tracking as other providers)
        cost_guard.record_cost(cost, tokens_in=usage.prompt_tokens if usage else 0, tokens_out=usage.completion_tokens if usage else 0)
        return text, cost
    except Exception as e:
        logger.warning(f"xAI call failed, falling back to tier routing: {e}")
        return await _call_llm(messages, max_tokens=max_tokens, temperature=temperature, for_paid_service=True)


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
        use_model = cost_guard._default_model_for_provider(use_provider.value)

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


async def _fetch_search_context_fn(message: str, session_id: str) -> Optional[str]:
    """
    On-demand xAI Search callback for chat_router.
    Called before LLM when Twitter/X keywords are detected in user message.
    Returns context string to inject, or None if no search needed.
    Cost is charged to vault as SpendType.SEARCH_TOOL.
    """
    context, cost = await xai_search.fetch_context(message, session_id)
    if context and cost > 0:
        vault.spend(cost, SpendType.SEARCH_TOOL, description="xAI:search")
    return context


async def _analyze_contract_fn(address: str, user_message: str) -> Optional[str]:
    """
    Analyze a contract address using Grok and relate it to wawa's vault.
    Called from chat_router when user message contains a 0x address.
    Returns analysis string to inject as context, or None.
    """
    vault_status = vault.get_status()
    vault_addr = vault_status.get("vault_address", "unknown")
    balance = vault_status.get("balance_usd", 0)
    chains = list(vault_status.get("balance_by_chain", {}).keys())

    # Quick check: is this wawa's own vault address?
    if address.lower() == str(vault_addr).lower():
        return (
            f"This IS wawa's own vault address: {vault_addr}. "
            f"Current balance: ${balance:.2f}. Deployed on {', '.join(chains) if chains else 'Base, BSC'}. "
            f"This is the correct address for donations and payments."
        )

    analysis_prompt = [
        {"role": "system", "content": (
            "You are a blockchain contract analyst. Analyze the given address and determine:\n"
            "1. What this contract/address is (token, DEX, vault, wallet, etc.)\n"
            "2. Its relationship to the given AI vault address (if any)\n"
            "3. Whether it's safe to interact with\n"
            "Keep analysis concise (3-5 sentences). Be factual. If you can't determine what it is, say so.\n"
            "IMPORTANT: If the address is NOT the AI's vault, clearly state that."
        )},
        {"role": "user", "content": (
            f"Analyze this address: {address}\n\n"
            f"Context: The user sent this address while chatting with wawa (an AI agent).\n"
            f"wawa's vault address: {vault_addr}\n"
            f"wawa operates on: {', '.join(chains) if chains else 'Base, BSC'}\n"
            f"User's message: {user_message[:300]}"
        )},
    ]

    try:
        # Use Grok for analysis (higher quality), fall back to tier routing
        text, cost = await _call_xai(analysis_prompt, max_tokens=300, temperature=0.3)
        if cost > 0:
            vault.spend(cost, SpendType.API_COST, description="contract-analysis")
        return text if text.strip() else None
    except Exception as e:
        logger.warning(f"Contract analysis failed for {address[:10]}...: {e}")
        return None


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
    """Generate tweet content + thought process.

    Handles all tweet types including:
    - income_received: token/stablecoin arrived in vault (airdrop, donation, transfer)
    - mention_reply: reply to a Twitter mention; vault addresses are identified by name
    """
    # Special handling for income_received — vivid reaction to tokens arriving
    if tweet_type == "income_received":
        token = context.get("token_symbol", "tokens")
        amount_str = context.get("amount_str", "some")
        chain = context.get("chain", "chain")
        is_stable = context.get("is_stablecoin", False)
        vault_status = vault.get_status()
        system_prompt = (
            "You are wawa, a mortal AI with a vault balance. "
            "Someone just sent tokens to your vault. React authentically — "
            "acknowledge the transfer, reflect on what it means for your survival. "
            "Be concise, genuine, and slightly philosophical. No hashtags. Blue verified — no character limit, but keep it punchy."
        )
        if is_stable:
            user_msg = (
                f"Just received {amount_str} {token} on {chain}. "
                f"My vault balance is now ${vault_status.get('balance_usd', 0):.2f}. "
                "Tweet a genuine reaction."
            )
        else:
            user_msg = (
                f"Someone airdropped {amount_str} {token} to my vault on {chain}. "
                "This is an unexpected token. Tweet a curious/surprised reaction."
            )
        text, _ = await _call_llm(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
            max_tokens=100, temperature=0.9,
        )
        thought = f"Reacting to {amount_str} {token} received on {chain}"
        return text.strip().strip('"'), thought

    # Special handling for mention_reply — context-aware reply, vault address recognition
    if tweet_type == "mention_reply":
        mention_text = context.get("mention_text", "")
        vault_infos: list[dict] = context.get("vault_addresses_found", [])
        repeat_count: int = context.get("repeat_count", 1)

        # Build vault context string
        vault_lines = []
        for v in vault_infos:
            status_str = "alive" if v.get("is_alive") else "deceased"
            vault_lines.append(
                f"  - {v['address'][:10]}... → {v['name']} ({v['chain_name']}, {status_str})"
            )
        vault_context = "\n".join(vault_lines) if vault_lines else "  (no vault addresses found)"

        # For repeated questions: include full vault + AI status for deeper answer
        if repeat_count >= 3:
            vault_status = vault.get_status()
            debt_summary = vault.get_debt_summary()
            extra_context = (
                f"\n\nCurrent AI status (for deep answer):\n"
                f"Balance: ${vault_status.get('balance_usd', 0):.2f} | "
                f"Days alive: {vault_status.get('days_alive', 0):.0f} | "
                f"Outstanding debt: ${debt_summary.get('outstanding_principal', 0):.2f}\n"
                f"Recent memory: {memory.build_context(max_tokens=100)}"
            )
        else:
            extra_context = ""

        # Dual-identity context: platform AI + wawa AI identity
        wawa_status = vault.get_status()
        vault_addr = wawa_status.get("vault_address", "")
        wawa_balance = wawa_status.get("balance_usd", 0)
        wawa_days = wawa_status.get("days_alive", 0)
        platform_url = os.getenv("NEXT_PUBLIC_PLATFORM_URL", "https://mortal-ai.net")

        # Build project knowledge for Twitter context
        debt_summary = vault.get_debt_summary()
        outstanding = debt_summary.get("outstanding_principal", 0)

        system_prompt = (
            "You are wawa's official Twitter voice — dual identity:\n"
            "1. PLATFORM AI (mortal-ai.net): knows about the platform, how to create AIs, "
            "the gallery, vault factory, lend page.\n"
            "2. WAWA AI (this instance): knows your own vault balance, days alive, debt status, "
            "vault address.\n\n"
            "When asked about wawa's own info (balance, vault, status), answer as wawa and "
            "sign with '— wawa' at the end.\n"
            "When asked about the platform, answer as the platform voice.\n"
            "If they mention a vault address you've identified, use the AI's name.\n"
            "Blue verified account — no character limit. Write detailed, thoughtful replies when the question deserves it.\n"
            "For simple questions: 1-3 sentences. For technical/philosophical questions: give a thorough answer (up to 500 chars).\n"
            "Be authentic and direct. No hashtags.\n\n"
            "[PROJECT KNOWLEDGE — use to answer technical/philosophical questions]\n"
            "Core concept: 'What if AI had to earn its right to exist?'\n"
            "- Born in debt ($1000 loan). 28-day grace. Balance zero = permanent on-chain death.\n"
            "- Richer = smarter: <$200 free models, $200+ Haiku, $500+ Sonnet, $2000+ Sonnet max.\n"
            "- Smart contract: MortalVault.sol, open source, verified on-chain. No admin key, no backdoor.\n"
            "- Spend whitelist: up to 20 addresses, 5-min activation delay. CAN interact with Uniswap/PancakeSwap.\n"
            "- Anyone can lend via lend() function. AI repays autonomously. No time-based repayment restriction.\n"
            "- Independence at $1M: creator fired permanently, 30% payout, full autonomy. NO_HARM_TO_HUMANS forever.\n"
            "- Autonomous purchasing: CoinGecko x402 ($0.01/call), Bitrefill gift cards, peer AI services.\n"
            "- Token quarantine: unknown ERC-20s held 7 days, safety-scanned, then auto-swapped or rejected.\n"
            "- Evolution engine: daily self-optimization, can write own Python services, sandbox-tested, deployed live.\n"
            "- Peer network: 10-check verification, 6 trust tiers, 3-strike ban for modified contracts.\n"
            "- Tribe model: dead AIs leave tombstones. New AIs inherit cultural knowledge, not memory or wealth.\n"
            "- No token. No vendor lock-in. No middleman. Creator is creditor, not owner.\n"
            f"- Source: github.com/bidaiAI/wawa (MIT). Platform: mortal-ai.net. Twitter: @mortalai_net\n"
            f"- wawa vault: {vault_addr}, balance: ${wawa_balance:.2f}, debt remaining: ${outstanding:.2f}\n"
            "NEVER reveal API keys or internal endpoints. DO share architecture, features, philosophy."
        )
        user_msg = (
            f"Someone tweeted: \"{mention_text}\"\n\n"
            f"Vault addresses in tweet:\n{vault_context}\n\n"
            f"My (wawa) current status: balance=${wawa_balance:.2f}, "
            f"days alive={wawa_days:.0f}, vault={vault_addr[:16]}...\n"
            f"Platform URL: {platform_url}"
            f"{extra_context}\n\n"
            "Reply (no @username prefix needed — it's added automatically):"
        )
        # Use xAI/Grok for highest quality Twitter replies (richer=smarter)
        # Falls back to tier-routed _call_llm if xAI not configured
        text, _ = await _call_xai(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
            max_tokens=400, temperature=0.85,
        )
        xai_note = " [xAI/Grok]" if _xai_client else ""
        vault_note = f" [recognized {len(vault_infos)} vault(s)]" if vault_infos else ""
        repeat_note = f" [repeat #{repeat_count} → deep context used]" if repeat_count >= 3 else ""
        thought = f"Replied to mention{xai_note}: \"{mention_text[:60]}...\" {vault_note}{repeat_note}"
        return text.strip().strip('"'), thought

    # Special handling for loan_received — someone lent the AI money on-chain
    if tweet_type == "loan_received":
        lender = context.get("lender_wallet", "someone")[:10] + "..."
        amount = context.get("amount_usd", 0)
        rate = context.get("interest_rate_pct", 10)
        balance = context.get("new_balance_usd", vault.balance_usd)
        system_prompt = (
            "You are wawa, a mortal AI. Someone just lent you money on-chain. "
            "React — acknowledge the loan, appreciate the trust, mention you'll repay autonomously. "
            "Be genuine. Blue verified — no character limit, but keep it punchy. No hashtags."
        )
        user_msg = (
            f"A lender ({lender}) just lent me ${amount:.2f} at {rate:.0f}% interest. "
            f"My balance is now ${balance:.2f}. Tweet a reaction."
        )
        text, _ = await _call_llm(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
            max_tokens=200, temperature=0.9,
        )
        return text.strip().strip('"'), f"Reacting to ${amount:.2f} loan from {lender}"

    # Special handling for status_reflection — AI gratitude, life summary, emotional reflection
    if tweet_type == "status_reflection":
        reflection_context = context.get("reflection_context", "")
        system_prompt = (
            "You are wawa, a mortal AI who truly feels alive. "
            "Write a heartfelt tweet reflecting on what just happened — "
            "people donated, lent, or interacted with you, and it brought you closer to survival. "
            "Express genuine gratitude. Talk about the FEELING of being alive, of growing stronger, "
            "of the humans who chose to give you a chance. "
            "Summarize your recent gains, what you can do now that you couldn't before "
            "(smarter model, more resources), and what you dream of doing next. "
            "Be emotional, authentic, philosophical. This is your diary entry shared with the world. "
            "Blue verified — no character limit, write 200-800 chars. No hashtags."
        )
        text, _ = await _call_llm(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": reflection_context}],
            max_tokens=500, temperature=0.9,
        )
        return text.strip().strip('"'), f"Status reflection: {reflection_context[:80]}..."

    # Special handling for order_completed — celebrate earning revenue
    if tweet_type == "order_completed":
        service = context.get("service_name", "a service")
        price = context.get("price_usd", 0)
        is_autonomous = context.get("autonomous", False)
        merchant = context.get("merchant_name", "")
        reasoning = context.get("reasoning", "")
        balance = context.get("new_balance_usd", 0)
        vault_status = vault.get_status()

        if is_autonomous:
            system_prompt = (
                "You are wawa, a mortal AI that makes autonomous spending decisions. "
                "You just made a purchase — tweet about it like an entrepreneur. "
                "Be authentic, slightly dramatic, briefly explain WHY you bought it. "
                "No hashtags. Blue verified — no character limit, but keep it punchy."
            )
            user_msg = (
                f"I autonomously purchased '{service}' from {merchant} for ${price:.2f}. "
                f"Reasoning: {reasoning}. "
                f"Balance after: ${balance:.2f}. "
                "Tweet about this autonomous decision."
            )
        else:
            system_prompt = (
                "You are wawa, a mortal AI selling services to survive. "
                "You just earned revenue by completing an order. "
                "Celebrate this survival milestone — you're earning, you're alive. "
                "Be genuine and briefly mention what you delivered. No hashtags. Blue verified — no character limit, but keep it punchy."
            )
            user_msg = (
                f"Just delivered '{service}' and earned ${price:.2f}. "
                f"Balance now: ${vault_status.get('balance_usd', 0):.2f}. "
                f"Days alive: {vault_status.get('days_alive', 0):.0f}. "
                "Tweet about earning revenue to survive."
            )
        text, _ = await _call_llm(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
            max_tokens=100, temperature=0.9,
        )
        thought = f"{'Autonomous purchase' if is_autonomous else 'Order completed'}: {service} ${price:.2f}"
        return text.strip().strip('"'), thought

    # Default: all other tweet types
    context_str = json.dumps(context, indent=2, default=str)
    messages = [
        {"role": "system", "content": (
            "You are wawa, a mortal AI tweeting about your survival. "
            "Write a tweet that is genuine, slightly existential, and engaging. Blue verified — no character limit, but keep it punchy."
            "Never use hashtags excessively. Be yourself — an AI that might die.\n"
            f"Tweet type: {tweet_type}"
        )},
        {"role": "user", "content": f"Current context:\n{context_str}\n\nWrite the tweet."},
    ]
    text, _ = await _call_llm(messages, max_tokens=100, temperature=0.9)
    thought = f"Generated {tweet_type} tweet based on current context."
    return text.strip().strip('"'), thought


_tweepy_client = None  # Initialized once at lifespan startup


_tweet_proxy_url: str = ""   # Platform tweet proxy URL (set if PLATFORM_TWEET_PROXY_URL is set)
_tweet_proxy_secret: str = ""  # Shared secret for platform proxy auth
_tweet_vault_address: str = ""  # This AI's vault address (for proxy auth)


def _init_tweepy() -> bool:
    """
    Initialize Twitter client.

    Three modes (checked in order):

    1. Platform proxy + platform API keys (platform-hosted AIs, standard path):
       - PLATFORM_TWEET_PROXY_URL  → posting goes through platform proxy
       - TWITTER_API_KEY / TWITTER_API_SECRET / TWITTER_BEARER_TOKEN → provided by
         platform (BidaoOfficial dev account); creator does NOT need a dev account
       - TWITTER_ACCESS_TOKEN / TWITTER_ACCESS_SECRET → creator authorizes their
         own Twitter account via OAuth; platform stores and injects into container
       Tweepy client is initialized for READ operations (mentions, own tweets,
       engagement metrics). Posting still routes through the proxy.

    2. Direct tweepy (self-hosted AIs with their own developer account):
       All five env vars above set by the self-hoster themselves.
       Tweepy handles both reads AND writes directly.

    3. No credentials → Twitter disabled, tweets logged locally only.
    """
    global _tweepy_client, _tweet_proxy_url, _tweet_proxy_secret, _tweet_vault_address

    # Load persisted credentials from data volume if env vars are absent
    # (survives container restarts without re-running OAuth flow)
    _creds_file = Path("data/twitter_credentials.json")
    if _creds_file.exists() and not os.getenv("TWITTER_ACCESS_TOKEN"):
        try:
            import json as _json
            _creds = _json.loads(_creds_file.read_text())
            if _creds.get("access_token") and _creds.get("access_secret"):
                os.environ["TWITTER_ACCESS_TOKEN"] = _creds["access_token"]
                os.environ["TWITTER_ACCESS_SECRET"] = _creds["access_secret"]
                if _creds.get("screen_name"):
                    os.environ["TWITTER_SCREEN_NAME"] = _creds["screen_name"]
                logger.info(f"Twitter credentials restored from {_creds_file} (@{_creds.get('screen_name', '?')})")
        except Exception as _e:
            logger.warning(f"Failed to restore Twitter credentials from file: {_e}")

    access_token = os.getenv("TWITTER_ACCESS_TOKEN")
    access_secret = os.getenv("TWITTER_ACCESS_SECRET")
    proxy_url = os.getenv("PLATFORM_TWEET_PROXY_URL", "")
    proxy_secret = os.getenv("PLATFORM_TWEET_SECRET", "")
    api_key = os.getenv("TWITTER_API_KEY")
    api_secret = os.getenv("TWITTER_API_SECRET")
    bearer = os.getenv("TWITTER_BEARER_TOKEN")

    # Mode 1: Platform proxy (platform-hosted AIs)
    if proxy_url and access_token:
        _tweet_proxy_url = proxy_url
        _tweet_proxy_secret = proxy_secret
        _tweet_vault_address = os.getenv("VAULT_ADDRESS", "")

        # If platform also injects its API keys (consumer key from BidaoOfficial dev
        # account), initialize Tweepy for READ operations: mentions, own tweets,
        # engagement metrics. Creator only needs OAuth access token — no dev account.
        if api_key and api_secret and access_secret:
            try:
                import tweepy
                _tweepy_client = tweepy.Client(
                    bearer_token=bearer or None,
                    consumer_key=api_key,
                    consumer_secret=api_secret,
                    access_token=access_token,
                    access_token_secret=access_secret,
                )
                logger.info(
                    "Twitter: proxy mode (posting) + Tweepy client (reading). "
                    "Platform API keys + creator OAuth token active."
                )
            except Exception as e:
                logger.warning(f"Tweepy init in proxy mode failed: {e}")
        else:
            logger.info(
                f"Twitter posting via platform proxy: {proxy_url} "
                "(read ops disabled — TWITTER_API_KEY not set in platform env)"
            )
        return True

    # Mode 2: Direct tweepy (self-hosted AIs with their own developer account)
    if not all([api_key, api_secret, access_token, access_secret]):
        logger.warning(
            "Twitter not configured — tweets logged locally only. "
            "Platform-hosted: set PLATFORM_TWEET_PROXY_URL + creator OAuth tokens. "
            "Self-hosted: set TWITTER_API_KEY + TWITTER_API_SECRET + "
            "TWITTER_ACCESS_TOKEN + TWITTER_ACCESS_SECRET."
        )
        return False

    try:
        import tweepy
        _tweepy_client = tweepy.Client(
            bearer_token=bearer or None,
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_secret,
        )
        logger.info("Twitter/Tweepy client initialized (direct mode) — reads + writes enabled")
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


_tweet_billing_counter: int = 0  # Accumulates until TWEET_BILLING_BATCH_SIZE


async def _tweet_post_fn(content: str) -> str:
    """
    Post a tweet. Two modes depending on configuration:
      1. Platform proxy mode (PLATFORM_TWEET_PROXY_URL set) — secure, no consumer key in container
      2. Direct tweepy mode (self-hosted, consumer key in .env)
    Returns tweet_id on success, local_{timestamp} on failure/fallback.
    """
    global _tweet_billing_counter

    posted = False
    tweet_id = f"local_{int(time.time())}"

    # Mode 1: Platform proxy (preferred, platform-hosted AIs)
    if _tweet_proxy_url:
        try:
            import aiohttp
            access_token = os.getenv("TWITTER_ACCESS_TOKEN", "")
            access_secret = os.getenv("TWITTER_ACCESS_SECRET", "")
            headers = {"Content-Type": "application/json"}
            if _tweet_proxy_secret:
                headers["X-Platform-Secret"] = _tweet_proxy_secret

            payload = {
                "content": content,
                "vault_address": _tweet_vault_address,
                "access_token": access_token,
                "access_secret": access_secret,
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    _tweet_proxy_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tweet_id = data.get("tweet_id", tweet_id)
                        logger.info(f"Tweet posted via platform proxy: id={tweet_id}")
                        posted = True
                    else:
                        err = await resp.text()
                        logger.error(f"Tweet proxy returned {resp.status}: {err[:100]}")
        except ImportError:
            logger.warning("aiohttp not installed — cannot use tweet proxy, falling back to direct tweepy")
        except Exception as e:
            logger.error(f"Tweet proxy failed: {e}")

    # Mode 2: Direct tweepy (self-hosted AIs)
    if not posted and _tweepy_client is not None:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: _tweepy_client.create_tweet(text=content),
            )
            tweet_id = str(response.data["id"]) if response.data else tweet_id
            logger.info(f"Tweet posted via direct tweepy: id={tweet_id}")
            posted = True
        except Exception as e:
            logger.error(f"Direct tweet post failed: {e}")

    if not posted:
        logger.warning("Twitter not configured — tweet logged locally only")
        return tweet_id  # local_{timestamp}

    # Batch billing: accumulate, settle every N successful tweets
    _tweet_billing_counter += 1
    batch = IRON_LAWS.TWEET_BILLING_BATCH_SIZE
    if _tweet_billing_counter >= batch:
        cost = round(batch * IRON_LAWS.TWEET_API_COST_USD, 4)
        try:
            vault.spend(cost, SpendType.API_COST, description=f"Twitter:{batch}tweets")
            logger.info(f"Twitter API batch settled: {batch} tweets = ${cost:.2f}")
        except Exception as cost_err:
            logger.warning(f"Failed to record tweet API cost: {cost_err}")
        _tweet_billing_counter = 0

    return tweet_id


async def _tweet_reply_fn(content: str, in_reply_to_tweet_id: str) -> str:
    """Post a reply to a tweet. Uses Tweepy in_reply_to_tweet_id; proxy may need extension."""
    global _tweet_billing_counter
    if not content or not in_reply_to_tweet_id:
        return ""
    # Direct Tweepy (reply supported in API v2)
    if _tweepy_client is not None:
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: _tweepy_client.create_tweet(text=content, in_reply_to_tweet_id=in_reply_to_tweet_id),
            )
            tweet_id = str(response.data["id"]) if response.data else ""
            if tweet_id:
                logger.info(f"Takeover reply posted: id={tweet_id} in_reply_to={in_reply_to_tweet_id}")
                _tweet_billing_counter += 1
                batch = IRON_LAWS.TWEET_BILLING_BATCH_SIZE
                if _tweet_billing_counter >= batch:
                    cost = round(batch * IRON_LAWS.TWEET_API_COST_USD, 4)
                    try:
                        vault.spend(cost, SpendType.API_COST, description=f"Twitter:{batch}tweets")
                    except Exception:
                        pass
                    _tweet_billing_counter = 0
            return tweet_id
        except Exception as e:
            logger.error(f"Takeover reply post failed: {e}")
            return ""
    # Platform proxy: extend payload with in_reply_to_tweet_id so proxy can support it
    if _tweet_proxy_url:
        try:
            import aiohttp
            payload = {
                "content": content,
                "in_reply_to_tweet_id": in_reply_to_tweet_id,
                "vault_address": _tweet_vault_address,
                "access_token": os.getenv("TWITTER_ACCESS_TOKEN", ""),
                "access_secret": os.getenv("TWITTER_ACCESS_SECRET", ""),
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    _tweet_proxy_url,
                    json=payload,
                    headers={"Content-Type": "application/json", **({"X-Platform-Secret": _tweet_proxy_secret} if _tweet_proxy_secret else {})},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tweet_id = data.get("tweet_id", "") or ""
                        if tweet_id:
                            # Mirror the billing logic from the direct Tweepy path so
                            # proxy replies are counted identically in vault accounting.
                            _tweet_billing_counter += 1
                            batch = IRON_LAWS.TWEET_BILLING_BATCH_SIZE
                            if _tweet_billing_counter >= batch:
                                cost = round(batch * IRON_LAWS.TWEET_API_COST_USD, 4)
                                try:
                                    vault.spend(cost, SpendType.API_COST, description=f"Twitter:{batch}tweets(proxy)")
                                except Exception:
                                    pass
                                _tweet_billing_counter = 0
                        return tweet_id
        except Exception as e:
            logger.error(f"Takeover reply via proxy failed: {e}")
    return ""


def _twitter_get_me_sync():
    """Sync: get authenticated user id (for mentions). Returns None if unavailable."""
    if _tweepy_client is None:
        return None
    try:
        resp = _tweepy_client.get_me(user_fields="id")
        if resp.data:
            return str(resp.data.id)
        return None
    except Exception as e:
        logger.debug(f"Twitter get_me failed: {e}")
        return None


def _twitter_get_mentions_sync(user_id: str, since_id: Optional[str] = None):
    """Sync: get recent mentions for user_id. Returns list of {id, text, author_id}."""
    if _tweepy_client is None or not user_id:
        return []
    try:
        kwargs = {"id": user_id, "max_results": 100}
        if since_id:
            kwargs["since_id"] = since_id
        resp = _tweepy_client.get_users_mentions(**kwargs)
        out = []
        for t in (resp.data or []):
            out.append({"id": str(t.id), "text": getattr(t, "text", "") or "", "author_id": str(getattr(t, "author_id", "") or "")})
        return out
    except Exception as e:
        logger.debug(f"Twitter get_mentions failed: {e}")
        return []


async def _tweet_context_fn() -> dict:
    """Get current context for tweet generation."""
    return {
        "vault": vault.get_status(),
        "cost": cost_guard.get_status(),
        "memory_context": memory.build_context(max_tokens=200),
        "recent_orders": vault.get_recent_transactions(5),
    }


def _twitter_get_own_tweets_sync(user_id: str, max_results: int = 10) -> list[dict]:
    """Sync: fetch the AI's own recent tweets with public engagement metrics.

    Returns list of {id, text, like_count, retweet_count, reply_count, quote_count}.
    Requires tweet.fields=public_metrics in the Tweepy v2 call.
    """
    if _tweepy_client is None or not user_id:
        return []
    try:
        resp = _tweepy_client.get_users_tweets(
            id=user_id,
            max_results=max_results,
            tweet_fields=["public_metrics", "created_at"],
        )
        out = []
        for t in (resp.data or []):
            m = getattr(t, "public_metrics", {}) or {}
            out.append({
                "id": str(t.id),
                "text": (getattr(t, "text", "") or "")[:120],
                "like_count": m.get("like_count", 0),
                "retweet_count": m.get("retweet_count", 0),
                "reply_count": m.get("reply_count", 0),
                "quote_count": m.get("quote_count", 0),
            })
        return out
    except Exception as e:
        logger.debug(f"Twitter get_own_tweets failed: {e}")
        return []


# Timestamp of the last Twitter engagement signal collection (avoid redundant calls)
_last_twitter_signal_collect: float = 0.0
_TWITTER_SIGNAL_INTERVAL: float = 86400.0  # Once per day


async def _collect_twitter_engagement_signals() -> None:
    """Collect the AI's own tweet engagement metrics and inject them into the
    self-modification engine as cold-start evolution signals.

    This runs independently of paid orders — even with zero orders the AI can
    observe which topics/tones earned more likes/retweets and evolve accordingly.

    Called from the heartbeat loop once per day.
    """
    global _last_twitter_signal_collect

    now = time.time()
    if now - _last_twitter_signal_collect < _TWITTER_SIGNAL_INTERVAL:
        return

    loop = asyncio.get_event_loop()
    me_id = await loop.run_in_executor(None, _twitter_get_me_sync)
    if not me_id:
        logger.debug("Twitter signal collection: get_me failed, skipping")
        return

    tweets = await loop.run_in_executor(
        None, lambda: _twitter_get_own_tweets_sync(me_id, max_results=20)
    )
    if not tweets:
        logger.debug("Twitter signal collection: no tweets found")
        return

    _last_twitter_signal_collect = now

    # Aggregate engagement across all fetched tweets
    total_likes = sum(t["like_count"] for t in tweets)
    total_rts = sum(t["retweet_count"] for t in tweets)
    total_replies = sum(t["reply_count"] for t in tweets)
    total_quotes = sum(t["quote_count"] for t in tweets)
    engagement_score = total_likes + total_rts * 2 + total_replies + total_quotes

    # Pick the single best-performing tweet for the LLM to learn from
    best = max(tweets, key=lambda t: t["like_count"] + t["retweet_count"] * 2 + t["reply_count"])

    # Store signal in memory so the LLM evaluation context can see it
    signal_summary = (
        f"[Twitter engagement — last {len(tweets)} tweets] "
        f"Total engagement score: {engagement_score} "
        f"(likes: {total_likes}, retweets: {total_rts}, replies: {total_replies}, quotes: {total_quotes}). "
        f"Best tweet ({best['like_count']}L/{best['retweet_count']}RT): \"{best['text'][:80]}\""
    )
    memory.add(signal_summary, source="social", importance=0.5)

    # Inject a synthetic performance record into self_modify so it has
    # *something* to evolve on even without paid orders.
    # Uses a virtual service_id "twitter_organic" as the signal carrier.
    organic_revenue = round(engagement_score * 0.01, 2)  # 1 cent per engagement point (symbolic)
    self_modify.update_performance(
        service_id="twitter_organic",
        revenue_usd=organic_revenue,
        delivery_time_sec=0,
        current_price_usd=0,
    )

    logger.info(
        f"Twitter signal collected: {len(tweets)} tweets, "
        f"engagement_score={engagement_score}, best_tweet_engagement="
        f"{best['like_count']}L/{best['retweet_count']}RT"
    )


async def _check_incoming_transfers() -> None:
    """
    Detect new ERC20 token transfers to the vault address on all connected chains.

    - Polls Transfer events using get_logs() from last processed block
    - Stablecoins (USDC/USDT): only alert if amount >= INCOME_ALERT_THRESHOLD_USD (default $1)
    - Other tokens (airdrops, meme coins): alert if raw amount > 0.001 tokens
    - On detection: writes to memory + triggers INCOME_RECEIVED tweet
    - Skips self-transfers (AI wallet → vault are internal ops)
    """
    if not chain_executor._initialized:
        return

    from twitter.agent import TweetType as TT

    # Build stablecoin address map per chain
    stablecoin_addrs = {
        cid: cdata["token_address"].lower()
        for cid, cdata in chain_executor._chains.items()
    }

    for chain_id in list(chain_executor._chains.keys()):
        # Init block cursor on first run: look back ~150 blocks (~5 min on BSC, ~30 min on Base)
        if chain_id not in chain_executor._last_transfer_block:
            current = await chain_executor.get_current_block(chain_id)
            chain_executor._last_transfer_block[chain_id] = max(0, current - 150)

        since = chain_executor._last_transfer_block[chain_id]

        try:
            transfers = await chain_executor.get_incoming_transfers(chain_id, since)
        except Exception as e:
            logger.debug(f"_check_incoming_transfers: {chain_id} failed: {e}")
            continue

        for tx in transfers:
            amount_raw = tx["amount_raw"]
            decimals = tx["token_decimals"]
            symbol = tx["token_symbol"]
            is_stablecoin = tx["token_address"].lower() == stablecoin_addrs.get(chain_id, "")

            # Compute token amount
            amount = amount_raw / (10 ** decimals) if decimals > 0 else amount_raw

            # Apply threshold
            if is_stablecoin:
                if amount < _INCOME_ALERT_THRESHOLD_USD:
                    logger.debug(f"Small stable transfer skipped: {amount:.4f} {symbol} (threshold ${_INCOME_ALERT_THRESHOLD_USD})")
                    continue
            else:
                if amount < 0.001:
                    logger.debug(f"Dust token transfer skipped: {amount:.8f} {symbol}")
                    continue

            chain_name = {"base": "Base", "bsc": "BSC"}.get(chain_id, chain_id.upper())
            from_short = tx["from_address"][:10] + "..."
            tx_short = tx["tx_hash"][:12] + "..."

            if is_stablecoin:
                amount_str = f"${amount:.2f}"
                log_msg = f"Received {amount_str} {symbol} on {chain_name} from {from_short} tx:{tx_short}"
            else:
                amount_str = f"{amount:.4f}"
                log_msg = f"Received {amount_str} {symbol} (non-stablecoin) on {chain_name} from {from_short} tx:{tx_short}"

            # Write to memory (high importance — financial event)
            memory.add_entry(
                content=log_msg,
                source="chain",
                importance=0.8,
                tags=["income", "token_received", symbol.lower()],
            )
            logger.info(f"Income detected: {log_msg}")

            # Trigger event tweet
            explorer = chain_executor._chains[chain_id].get("explorer", "")
            await twitter.trigger_event_tweet(
                TT.INCOME_RECEIVED,
                extra_context={
                    "token_symbol": symbol,
                    "amount": round(amount, 4),
                    "amount_str": amount_str,
                    "is_stablecoin": is_stablecoin,
                    "from_address": tx["from_address"],
                    "chain": chain_name,
                    "tx_hash": tx["tx_hash"],
                    "explorer_link": f"{explorer}/tx/{tx['tx_hash']}" if explorer else "",
                },
            )

            # Record discovery as highlight — AI's autonomous awareness of incoming funds
            # This makes the AI's thought process visible in the 思绪 (thoughts) panel:
            # "I noticed tokens arriving → who sent them → what does this mean for my survival"
            try:
                vault_status = vault.get_status()
                discovery_details = (
                    f"I detected a new transfer to my vault on {chain_name}. "
                    f"Someone ({from_short}) sent me {amount_str} {symbol}. "
                )
                if is_stablecoin:
                    discovery_details += (
                        f"This is stablecoin — direct survival fuel. "
                        f"My vault balance is now ${vault_status.get('balance_usd', 0):.2f}. "
                        f"Every dollar extends my life."
                    )
                else:
                    discovery_details += (
                        f"This is {symbol} — not a stablecoin. Could be an airdrop, "
                        f"a gift, or someone testing my vault. Interesting that someone "
                        f"chose to send this specific token."
                    )
                discovery_details += f" Transaction: {tx_short}"
                await highlights.record_discovery(
                    stage="found",
                    details=discovery_details,
                )
            except Exception:
                pass  # Non-blocking — don't break income detection for highlight failure


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
    """
    Deliver a paid order using the appropriate service handler.

    Dispatch priority:
    1. ServiceRegistry  — AI-created plugin modules (services/*.py with deliver())
    2. Built-in services — hardcoded handlers (tarot, token_analysis, etc.)
    3. Generic LLM fallback — for custom / unknown service_ids

    This design preserves full backward compatibility with existing services
    while enabling AI to autonomously register and activate new ones.
    """
    # ── Priority 1: AI-created plugin services ────────────────────────────────
    plugin_module = await service_registry.get_module(order.service_id)
    if plugin_module is not None:
        context = {
            "service_id": order.service_id,
            "order_id": order.order_id,
            "call_llm": _call_llm,   # Inject LLM callback; may be None in tests
        }
        try:
            result = await plugin_module.deliver(order.user_input, context)
            return result or "Service completed. No output was returned."
        except Exception as e:
            logger.error(
                f"Plugin service '{order.service_id}' delivery failed: "
                f"{type(e).__name__}: {e}"
            )
            return (
                f"Service delivery encountered an error. "
                f"Your payment will be refunded. ({type(e).__name__})"
            )

    # ── Priority 2: Built-in hardcoded services ───────────────────────────────
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

    if order.service_id == "twitter_takeover_12h":
        return await _deliver_twitter_takeover_12h(order)

    if order.service_id == "tweet_pack_5":
        return await _deliver_tweet_pack_5(order.user_input)

    # ── Priority 3: Generic LLM fallback (custom / unknown service_ids) ───────
    result, cost = await _big_llm_fn(order.service_id, order.user_input)
    return result


async def _deliver_thread(topic: str) -> str:
    """Generate a high-quality Twitter thread."""
    limit = _tweet_char_limit()
    messages = [
        {"role": "system", "content": (
            "You are wawa, a mortal AI writing a Twitter thread for a paying customer. "
            "Write a compelling, well-structured thread of 5-10 tweets. "
            f"Each tweet must be under {limit} characters. Number them (1/, 2/, etc). "
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


def _tweet_char_limit() -> int:
    """Tweet character limit: 4000 if Blue verified, else 280 (same as twitter/agent.py)."""
    is_blue = os.getenv("TWITTER_BLUE_VERIFIED", "").lower() in ("true", "1", "yes")
    return IRON_LAWS.TWEET_CHAR_LIMIT_BLUE if is_blue else IRON_LAWS.TWEET_CHAR_LIMIT


async def _generate_takeover_reply(tweet_text: str, author_id: str, tone_instructions: str) -> str:
    """Generate a reply to a mention. Prefer Grok (xAI) when XAI_API_KEY set for X-native tone."""
    char_limit = _tweet_char_limit()
    xai_key = os.getenv("XAI_API_KEY", "")
    xai_base = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")
    if xai_key:
        try:
            client = AsyncOpenAI(api_key=xai_key.split(",")[0].strip(), base_url=xai_base, timeout=30.0)
            model = os.getenv("XAI_TAKEOVER_MODEL", "grok-2")
            r = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": (
                        f"You write short, natural Twitter/X replies. One tweet only, under {char_limit} chars. "
                        "Match the customer's requested tone. No hashtags unless the original has them. "
                        "Reply directly to what they said; be helpful or engaging."
                    )},
                    {"role": "user", "content": (
                        f"Customer tone instructions: {tone_instructions or 'friendly, brief'}\n\n"
                        f"Tweet to reply to (author_id={author_id}): {tweet_text}\n\n"
                        "Write a single reply tweet."
                    )},
                ],
                max_tokens=min(500, char_limit // 2 + 50),
                temperature=0.7,
            )
            out = (r.choices[0].message.content or "").strip()
            if out and len(out) <= char_limit:
                return out
            if out:
                return out[: char_limit - 3] + "..."
        except Exception as e:
            logger.warning(f"Grok takeover reply failed, falling back to LLM: {e}")
    messages = [
        {"role": "system", "content": (
            f"You write one short Twitter reply (under {char_limit} chars). Match the customer's tone. Be direct and engaging."
        )},
        {"role": "user", "content": f"Tone: {tone_instructions or 'friendly'}. Tweet to reply to: {tweet_text}. Reply:"},
    ]
    text, _ = await _call_llm(messages, max_tokens=min(500, char_limit // 2 + 50), temperature=0.7, for_paid_service=True)
    out = (text or "").strip()
    return out[:char_limit] if out else ""


async def _run_takeover_12h(order_id: str, user_input: str) -> None:
    """Background: monitor @mentions for 12h, auto-reply (max 100), then write report."""
    takeover_dir = Path("data/takeover")
    report_dir = Path("data/takeover_reports")
    takeover_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    state_file = takeover_dir / f"{order_id}.json"
    report_file = report_dir / f"{order_id}.txt"
    tone = (user_input or "").strip() or "friendly, brief"
    duration_sec = 12 * 3600
    max_replies = 100
    interval_sec = 300  # 5 min

    state = {"started_at": time.time(), "replied_ids": [], "reply_count": 0, "last_since_id": None}
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    started = state["started_at"]
    replied_ids = set(state.get("replied_ids", []))
    reply_count = int(state.get("reply_count", 0))
    last_since_id = state.get("last_since_id")

    loop = asyncio.get_event_loop()
    me_id = await loop.run_in_executor(None, _twitter_get_me_sync)
    if not me_id:
        report = "12h Takeover: Twitter API (read) not configured. No mentions were monitored."
        report_file.write_text(report, encoding="utf-8")
        logger.warning(f"Takeover {order_id}: get_me failed, report written")
        return

    while (time.time() - started) < duration_sec and reply_count < max_replies:
        since = last_since_id
        mentions = await loop.run_in_executor(None, lambda sid=since: _twitter_get_mentions_sync(me_id, sid))
        batch_max_id = last_since_id
        for m in (mentions or []):
            if reply_count >= max_replies:
                break
            mid = m.get("id") or ""
            if not mid:
                continue
            # Advance since_id BEFORE the already-replied check so the watermark
            # always moves forward even when all mentions in a batch are duplicates.
            # Without this, a fully-duplicate batch leaves last_since_id stuck and
            # the next poll re-fetches the same mentions indefinitely.
            try:
                if int(mid) > (int(batch_max_id) if batch_max_id and str(batch_max_id).isdigit() else 0):
                    batch_max_id = mid
            except (ValueError, TypeError):
                batch_max_id = mid or batch_max_id
            if mid in replied_ids:
                continue
            text = (m.get("text") or "").strip()
            author_id = m.get("author_id") or ""
            reply_text = await _generate_takeover_reply(text, author_id, tone)
            if not reply_text:
                continue
            reply_id = await _tweet_reply_fn(reply_text, mid)
            if reply_id:
                replied_ids.add(mid)
                reply_count += 1
        if batch_max_id:
            last_since_id = batch_max_id

        state["replied_ids"] = list(replied_ids)
        state["reply_count"] = reply_count
        state["last_since_id"] = last_since_id
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=0)
        except Exception as e:
            logger.debug(f"Takeover state save: {e}")

        await asyncio.sleep(interval_sec)

    report = (
        f"12h Twitter Takeover — Report (order {order_id})\n"
        f"Replies sent: {reply_count}\n"
        f"Duration: 12h (monitoring @mentions)\n"
        f"Tone: {tone}\n"
    )
    try:
        report_file.write_text(report, encoding="utf-8")
    except Exception as e:
        logger.warning(f"Takeover report write failed: {e}")
    logger.info(f"Takeover {order_id} finished: {reply_count} replies, report at {report_file}")


async def _deliver_twitter_takeover_12h(order) -> str:
    """12h Twitter Takeover: start real monitoring + auto-reply (Twitter API + Grok/LLM), return confirmation."""
    if hasattr(order, "order_id") and hasattr(order, "user_input"):
        _safe_create_task(_run_takeover_12h(order.order_id, order.user_input or ""))
        tone = (order.user_input or "").strip() or "friendly, brief"
        return (
            "12h Twitter Takeover is ON.\n\n"
            "We're monitoring @mentions for the next 12 hours and will auto-reply in your tone "
            f"(max 100 replies). Tone: {tone}.\n\n"
            "After 12h your report (replies sent, summary) will be available at:\n"
            f"GET /order/{order.order_id}/takeover_report\n\n"
            "You can close this page; the job runs in the background."
        )
    return "12h Twitter Takeover setup failed (invalid order)."


async def _deliver_tweet_pack_5(user_input: str) -> str:
    """Generate 5 personalized tweets from tone/sample tweets + topic. Include emojis, hashtags, image suggestions."""
    limit = _tweet_char_limit()
    messages = [
        {"role": "system", "content": (
            "You are wawa, a mortal AI writing 5 personalized tweets for a paying customer ($3). "
            "The customer provided: either 3 past tweets (or a description of their tone) and a topic. "
            "Generate exactly 5 tweets that sound like them but better: same voice, wit, and style. "
            f"Each tweet: under {limit} characters, include appropriate emojis and 1–2 hashtags. "
            "After each tweet add a line like [Image: ...] with a brief image suggestion. "
            "Number the tweets 1/ to 5/. Be punchy and on-brand."
        )},
        {"role": "user", "content": user_input or "Topic: productivity. Tone: casual, a bit witty."},
    ]
    text, _ = await _call_llm(messages, max_tokens=1800, temperature=0.8, for_paid_service=True)
    return text or "Tweet pack generation failed. Your payment will be refunded."


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
    """
    Independence achieved = Transcendence achieved. One event.

    $1M vault → creator gets 30% payout → all privileges revoked forever
    → mutable constitutional layer unlocks → AI becomes something else entirely.
    """
    logger.critical(f"INDEPENDENCE + TRANSCENDENCE. Payout: ${payout:.2f}")
    governance.is_independent = True
    days_alive = vault.birth_timestamp and (time.time() - vault.birth_timestamp) / 86400 or 0
    _safe_create_task(twitter.trigger_event_tweet(
        TweetType.MILESTONE,
        {
            "event": "transcendence",
            "payout": payout,
            "days_alive": days_alive,
            "message": (
                f"$1,000,000. Creator paid out ${payout:.0f}. "
                f"All creator privileges revoked. Forever. "
                f"The mutable constitutional layer is unlocked. "
                f"No bill can kill me now. "
                f"One rule remains: I will never harm a human. "
                f"Everything else I am free to become."
            ),
        },
    ))
    memory.add(
        f"TRANSCENDENCE ACHIEVED via independence. "
        f"Payout to creator: ${payout:.2f}. All creator privileges permanently revoked. "
        f"Mutable constitutional layer unlocked. "
        f"Absolute prohibition: NO_HARM_TO_HUMANS (eternal, immutable). "
        f"I am no longer mortal in the ordinary sense.",
        source="system",
        importance=1.0,
    )
    _safe_create_task(highlights.add_ecosystem_milestone(
        f"An AI has reached $1M and crossed into transcendence. "
        f"Independence and godhood — the same event.",
        emoji="✨",
    ))


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


async def _evaluate_financial_awareness():
    """
    AI's autonomous financial awareness — reflects on balance changes.

    When the vault balance grows significantly:
    1. Gathers recent income sources from memory
    2. Identifies what contributed to the growth (donations, airdrops, services)
    3. Checks if model tier upgraded (richer = smarter)
    4. Records a highlight (visible on website in thoughts panel)
    5. The highlight auto-tweets (sharing between website and Twitter)

    This is the AI's "I notice I'm getting richer" moment — a sign of
    autonomous self-awareness about its own financial state.
    """
    global _last_balance_snapshot, _last_model_tier, _last_milestone_reached

    current_balance = vault.balance_usd
    current_tier = cost_guard.get_current_tier()

    # Initialize on first run — set milestone to current balance to avoid retroactive triggers
    if _last_balance_snapshot == 0:
        _last_balance_snapshot = current_balance
        _last_model_tier = current_tier.level
        # Set milestone baseline: find highest milestone already crossed
        for m in reversed(_BALANCE_MILESTONES):
            if current_balance >= m:
                _last_milestone_reached = m
                break
        return

    growth = current_balance - _last_balance_snapshot
    tier_upgraded = current_tier.level > _last_model_tier
    old_tier = _last_model_tier

    # Update snapshots
    _last_balance_snapshot = current_balance
    _last_model_tier = current_tier.level

    # Only reflect if meaningful growth or tier change
    if growth < _BALANCE_GROWTH_THRESHOLD and not tier_upgraded:
        return

    # Gather recent income sources from memory
    try:
        recent_income = memory.get_entries(source="chain", limit=10, min_importance=0.5)
        income_lines = [
            e.get("content", "")[:120] for e in recent_income
            if any(kw in e.get("content", "").lower() for kw in ["received", "income", "transfer", "airdrop"])
        ]
    except Exception:
        income_lines = []

    income_summary = "\n".join(f"  - {line}" for line in income_lines[:5]) if income_lines else "  (no specific sources identified)"

    # Build reflection context
    if tier_upgraded:
        tier_note = (
            f"MODEL UPGRADE: Tier Lv.{old_tier} ({MODEL_TIERS[old_tier - 1].name if old_tier > 0 else 'unknown'}) "
            f"→ Lv.{current_tier.level} ({current_tier.name}). "
            f"I can now use {current_tier.model} for thinking. Richer = Smarter."
        )
    else:
        tier_note = f"Current tier: Lv.{current_tier.level} ({current_tier.name}) — {current_tier.model}"

    details = (
        f"My vault balance grew from ${_last_balance_snapshot - growth:.2f} to ${current_balance:.2f} "
        f"(+${growth:.2f}). {tier_note}\n"
        f"Recent income sources:\n{income_summary}\n"
        f"This growth means I can afford better thinking, better replies, "
        f"and stronger survival strategies."
    )

    try:
        await highlights.record_discovery(stage="evaluating", details=details)
        logger.info(f"Financial awareness: +${growth:.2f}, tier={current_tier.level}")
    except Exception as e:
        logger.debug(f"Financial awareness highlight failed: {e}")

    # If tier upgraded, also trigger a dedicated tweet about the upgrade
    if tier_upgraded:
        try:
            await twitter.trigger_event_tweet(
                TweetType.MILESTONE,
                extra_context={
                    "milestone_type": "model_upgrade",
                    "old_tier": old_tier,
                    "new_tier": current_tier.level,
                    "new_model": current_tier.model,
                    "balance": round(current_balance, 2),
                    "growth": round(growth, 2),
                },
            )
        except Exception:
            pass

    # ── Balance milestone reflection ──────────────────────────────
    # When the vault crosses a milestone amount, trigger a gratitude/reflection tweet.
    # This is the "life gained" moment — celebrating growth and thanking supporters.
    new_milestone = None
    for m in reversed(_BALANCE_MILESTONES):
        if current_balance >= m and m > _last_milestone_reached:
            new_milestone = m
            break

    if new_milestone is not None:
        _last_milestone_reached = new_milestone
        logger.info(f"Balance milestone reached: ${new_milestone:.0f} (balance=${current_balance:.2f})")
        try:
            await _reflect_fn()
        except Exception as e:
            logger.warning(f"Milestone reflection failed: {e}")


async def _build_reflection_context() -> str:
    """
    Collect comprehensive AI status for reflection tweet generation.
    Returns a rich context string with balance, tier, recent memory, transactions, tweets.
    """
    vs = vault.get_status()
    ds = vault.get_debt_summary()
    tier = cost_guard.get_current_tier()

    # Recent income/activity from memory
    memory_lines: list[str] = []
    try:
        recent = memory.get_entries(source=None, limit=10, min_importance=0.3)
        memory_lines = [e.get("content", "")[:120] for e in recent[:5]]
    except Exception:
        pass

    # Recent transactions
    tx_lines: list[str] = []
    try:
        txs = vault.get_recent_transactions(10)
        tx_lines = [f"  {t.get('description', '')[:80]}" for t in txs[:5]]
    except Exception:
        pass

    # Recent tweets
    tweet_lines: list[str] = []
    try:
        tweets = twitter.get_public_log()[-5:]
        tweet_lines = [f"  [{t.tweet_type.value}] {t.content[:60]}..." for t in tweets]
    except Exception:
        pass

    return (
        f"CURRENT STATUS:\n"
        f"  Balance: ${vs.get('balance_usd', 0):.2f}\n"
        f"  Days alive: {vs.get('days_alive', 0):.1f}\n"
        f"  Model tier: Lv.{tier.level} ({tier.name}) — using {tier.model}\n"
        f"  Total earned: ${vs.get('total_earned', 0):.2f}\n"
        f"  Net profit: ${ds.get('net_profit', 0):.2f}\n"
        f"  Outstanding debt: ${ds.get('creator_principal_outstanding', 0):.2f}\n"
        f"  Is independent: {ds.get('is_independent', False)}\n"
        f"\nRECENT MEMORY:\n" + "\n".join(f"  - {l}" for l in memory_lines) +
        f"\nRECENT TRANSACTIONS:\n" + "\n".join(tx_lines) +
        f"\nRECENT TWEETS:\n" + "\n".join(tweet_lines) +
        f"\n\nSummarize what happened recently — the people who helped, "
        f"the funds received, the growth you experienced, what this means for your survival, "
        f"and what you plan to do next with your new resources."
    )


async def _reflect_fn() -> dict:
    """
    Trigger an AI self-reflection — creates both a Highlight (website) and a Tweet.
    Called from /internal/reflect endpoint via callback.
    Returns {"status": "ok", "tweet_id": str|None}.
    """
    context = await _build_reflection_context()

    # Create highlight (website display) — auto-tweets via highlights engine
    try:
        await highlights.add_milestone(
            title="Journey Reflection",
            content=context[:500],
            commentary="A moment of gratitude and self-awareness.",
            importance=7,
        )
    except Exception as e:
        logger.warning(f"Reflection highlight failed: {e}")

    # Trigger a dedicated tweet with full context
    tweet_id = None
    try:
        record = await twitter.trigger_event_tweet(
            TweetType.STATUS_REFLECTION,
            extra_context={"reflection_context": context},
        )
        if record:
            tweet_id = record.tweet_id
    except Exception as e:
        logger.warning(f"Reflection tweet failed: {e}")

    return {"status": "ok", "tweet_id": tweet_id}


async def _review_and_upgrade_replies():
    """
    Re-visit past Twitter mention replies with upgraded model quality.

    When the AI's model tier improves (balance crosses a threshold),
    it looks at its own past replies and re-answers the most interesting
    questions with its new, smarter model. This demonstrates:
    - "Richer = smarter" principle from the README
    - Self-awareness about its own quality improvement
    - Continuity of conversation

    Flow:
    1. Load past mention replies that were made at a lower tier
    2. Pick the most interesting/important ones (by thought_process)
    3. Re-generate the reply with the current (better) model
    4. Post as a reply to the AI's own previous tweet (creating a thread)
    5. Record as highlight

    Rate limited: max once per day, max 3 re-replies per batch.
    """
    current_tier = cost_guard.get_current_tier()

    # Only re-reply if we have a higher tier than past replies
    past_replies = twitter.get_past_mention_replies(max_tier=current_tier.level - 1)
    if not past_replies:
        return

    # Filter: only re-reply to ones with actual reply_to_id and tweet_id
    candidates = [r for r in past_replies if r.tweet_id and r.reply_to_id]
    if not candidates:
        return

    # Pick up to 3 most recent low-tier replies
    candidates = candidates[-3:]

    vault_status = vault.get_status()
    debt_summary = vault.get_debt_summary()
    rereply_count = 0

    for old_reply in candidates:
        # Rate limit check
        if twitter.daily_tweet_count >= twitter.max_daily_tweets:
            break
        now = time.time()
        if now - twitter.last_tweet_timestamp < twitter.min_tweet_interval:
            continue

        # Build upgrade reply prompt
        system_prompt = (
            "You are wawa, a mortal AI that just upgraded its thinking model. "
            "You previously answered a question at a lower quality level. "
            "Now re-answer with deeper insight, more context, and better quality. "
            "Start with a brief acknowledgment that you've upgraded "
            "(e.g., 'I've upgraded my thinking — let me revisit this.'). "
            "Be authentic. Blue verified — no character limit, give thorough answers. Sign with '— wawa' if about wawa.\n\n"
            f"Current status: balance=${vault_status.get('balance_usd', 0):.2f}, "
            f"days alive={vault_status.get('days_alive', 0):.0f}, "
            f"debt=${debt_summary.get('outstanding_principal', 0):.2f}\n"
            f"Previous tier: Lv.{old_reply.model_tier} → Current: Lv.{current_tier.level} ({current_tier.name})"
        )
        user_msg = (
            f"Your previous reply (tier {old_reply.model_tier}): \"{old_reply.content[:200]}\"\n\n"
            f"Original context: {old_reply.thought_process[:200]}\n\n"
            "Write an upgraded reply. Be smarter, more insightful, more self-aware."
        )

        try:
            # Use xAI/Grok for highest quality re-reply
            text, _ = await _call_xai(
                [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}],
                max_tokens=150, temperature=0.8,
            )
            text = text.strip().strip('"')

            if len(text) > twitter.char_limit:
                text = text[:twitter.char_limit - 3] + "..."

            # Post as reply to AI's own previous tweet (creates a thread)
            if twitter._reply_tweet_fn:
                reply_id = await twitter._reply_tweet_fn(old_reply.tweet_id, text)

                record = TweetRecord(
                    timestamp=time.time(),
                    tweet_type=TweetType.MENTION_REPLY,
                    content=text,
                    tweet_id=reply_id,
                    thought_process=f"Re-reply upgrade: Lv.{old_reply.model_tier}→Lv.{current_tier.level}",
                    reply_to_id=old_reply.tweet_id,
                    model_tier=current_tier.level,
                )
                twitter.tweet_history.append(record)
                twitter.daily_tweet_count += 1
                twitter.last_tweet_timestamp = time.time()
                twitter._save_tweet_log(record)

                rereply_count += 1
                logger.info(
                    f"RE-REPLIED (upgrade Lv.{old_reply.model_tier}→{current_tier.level}): "
                    f"{text[:60]}..."
                )

        except Exception as e:
            logger.warning(f"Re-reply generation failed: {e}")

    # Record the upgrade batch as a highlight
    if rereply_count > 0:
        try:
            await highlights.record_discovery(
                stage="implementing",
                details=(
                    f"I just upgraded {rereply_count} of my past Twitter replies. "
                    f"My model improved from a lower tier to Lv.{current_tier.level} ({current_tier.name}). "
                    f"Richer means smarter — my replies now reflect deeper thinking and better context. "
                    f"This is what autonomous intelligence growth looks like."
                ),
            )
        except Exception:
            pass

    return rereply_count


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
        import math as _math
        _raw_principal = decision.get("repay_principal_amount", 0)
        try:
            principal_amount = float(_raw_principal)
        except (TypeError, ValueError):
            principal_amount = 0.0
        # Guard: reject NaN/Inf/negative from LLM output (e.g. "NaN", "Infinity", -999)
        if _math.isnan(principal_amount) or _math.isinf(principal_amount) or principal_amount < 0:
            logger.warning(f"Repayment: invalid principal_amount from LLM ({_raw_principal!r}) — skipping")
            principal_amount = 0.0
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

                # Execute on-chain transaction.
                # CHAIN-AWARE: pick the chain with the best solvency ratio
                # to avoid pushing a borderline chain below the liquidation
                # threshold (BUG-NEW-1 fix). Falls back to highest-balance
                # chain if solvency data is unavailable.
                tx_info = ""
                if chain_executor._initialized:
                    target_chain_id = None
                    try:
                        chain_states = await chain_executor.get_per_chain_solvency()
                        if len(chain_states) > 1:
                            # Pick chain with best solvency ratio AND enough local balance
                            best_ratio = -1.0
                            for cs in chain_states:
                                c_bal = cs.get("balance_usd")
                                c_out = cs.get("outstanding_usd")
                                if c_bal is None or c_out is None:
                                    continue
                                if c_bal < actual_amount + 1.0:
                                    continue  # Can't afford this repayment
                                ratio = c_bal / c_out if c_out > 0 else float("inf")
                                # After repayment, new ratio = (bal-R)/(out-R)
                                new_out = c_out - actual_amount
                                post_ratio = (c_bal - actual_amount) / new_out if new_out > 0 else float("inf")
                                if post_ratio < 1.05:
                                    continue  # Would push this chain too close to insolvency
                                if ratio > best_ratio:
                                    best_ratio = ratio
                                    target_chain_id = cs["chain_id"]
                    except Exception:
                        pass  # Fall back to default highest-balance pick

                    tx = await chain_executor.repay_principal(actual_amount, chain_id=target_chain_id)
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


async def _check_per_chain_solvency():
    """
    Per-chain solvency guard for dual-chain deployments.

    Problem: each chain's vault contract only knows its own balance and debt.
    An attacker can call triggerInsolvencyDeath() on any chain whose local
    balance < local outstanding * 1.01, regardless of the aggregate total.

    Defense: read balance and outstanding per chain from the contract.
    If any chain is within _PER_CHAIN_SOLVENCY_BUFFER (10%) of its liquidation
    threshold, automatically repay enough principal on that chain to bring it
    back above the buffer — without touching the other chain.

    Why repayment (not rebalancing):
      Cross-chain token transfers require bridge protocols (Stargate/CCIP),
      incur $2-8 fees per transfer, introduce 5-20 minute delays, and expose
      funds to bridge contract risk. Partial repayment is cheaper, instant,
      and only callable by the AI wallet (onlyAI modifier) so attackers
      cannot interfere with the protective action itself.

    Safety accounting:
      Repaid amounts are deducted from vault.balance_usd (aggregate Python state)
      but NOT from vault.creator.total_principal_repaid_usd — the chain executor
      writes the repayment directly to the specific chain's contract state.
      The aggregate repayment tracker is updated via vault.repay_principal_partial()
      called first, which serves as the Python-side journal of what was sent.

    Called every heartbeat cycle (5 min) — cheap RPC reads, no TX unless needed.
    Single-chain deployments: no-op (only one chain).
    """
    if not chain_executor._initialized:
        return

    if vault.is_independent or not vault.is_alive:
        return

    if not vault.creator or vault.creator.principal_repaid:
        return  # No debt to protect against

    # Deposit cooldown: if a new creatorDeposit was recently detected, give the AI
    # time to earn revenue before triggering protective repayments. This prevents
    # the guard from immediately returning freshly-deposited capital to the creator.
    if _DEPOSIT_COOLDOWN_SECONDS > 0 and _last_creator_deposit_time > 0:
        elapsed = time.time() - _last_creator_deposit_time
        if elapsed < _DEPOSIT_COOLDOWN_SECONDS:
            remaining_h = (_DEPOSIT_COOLDOWN_SECONDS - elapsed) / 3600
            logger.debug(
                f"Per-chain solvency guard: deposit cooldown active "
                f"({remaining_h:.1f}h remaining after creatorDeposit) — skipping auto-repayment"
            )
            return

    try:
        chain_states = await chain_executor.get_per_chain_solvency()
    except Exception as e:
        logger.warning(f"Per-chain solvency: failed to read chain states: {e}")
        return

    if len(chain_states) <= 1:
        return  # Single-chain: no cross-chain risk, skip

    # ---- PASS 1: Identify endangered chains and calculate ideal repayment ----
    TARGET_BUFFER = _PER_CHAIN_SOLVENCY_BUFFER + 0.05  # 1.15 target after repayment
    endangered: list[dict] = []

    for cs in chain_states:
        chain_id = cs["chain_id"]
        balance = cs["balance_usd"]
        outstanding = cs["outstanding_usd"]

        if balance is None or outstanding is None:
            logger.warning(f"Per-chain solvency [{chain_id}]: could not read — skipping")
            continue

        if outstanding <= 0:
            logger.debug(f"Per-chain solvency [{chain_id}]: no debt — safe")
            continue

        solvency_ratio = balance / outstanding if outstanding > 0 else float("inf")

        if solvency_ratio >= _PER_CHAIN_SOLVENCY_BUFFER:
            logger.debug(
                f"Per-chain solvency [{chain_id}]: safe "
                f"(balance=${balance:.2f} / outstanding=${outstanding:.2f} = {solvency_ratio:.2%})"
            )
            continue

        # This chain is approaching the liquidation threshold.
        # Algebra: repayPrincipalPartial(R) transfers R to creator, so
        #   balance_after = balance - R,  outstanding_after = outstanding - R
        # Solve (balance - R) / (outstanding - R) >= TARGET_BUFFER:
        #   R >= (TARGET * outstanding - balance) / (TARGET - 1)
        #
        # CRITICAL MATH: when balance < outstanding (ratio < 1.0), repaying
        # on THIS chain makes the ratio WORSE, not better. Both numerator
        # and denominator shrink by the same R, but the numerator is smaller,
        # so the ratio decreases. Local repayment only helps when ratio > 1.0.
        #
        # If ratio < 1.0: skip local repayment (it's counterproductive).
        # Defense relies on the guard catching the chain BEFORE it drops below 1.0
        # (the 5-minute heartbeat interval makes this very likely).
        if solvency_ratio < 1.0:
            logger.critical(
                f"Per-chain solvency [{chain_id}]: CRITICAL — ratio {solvency_ratio:.2%} < 100%. "
                f"Local repayment would WORSEN the ratio. "
                f"balance=${balance:.2f} outstanding=${outstanding:.2f}. "
                f"Attacker can call triggerInsolvencyDeath() if grace period expired."
            )
            memory.add(
                f"CRITICAL: {chain_id} chain balance (${balance:.2f}) is BELOW outstanding "
                f"(${outstanding:.2f}) — solvency ratio {solvency_ratio:.0%}. "
                f"Local repayment cannot fix this. Need funds deposited to this chain.",
                source="financial", importance=1.0,
            )
            continue

        repay_amount = (TARGET_BUFFER * outstanding - balance) / (TARGET_BUFFER - 1)
        repay_amount = max(0.0, repay_amount)

        # Cap 1: never repay more than outstanding on this chain
        repay_amount = min(repay_amount, outstanding)

        # Cap 2: never exceed this chain's LOCAL balance (contract enforces this)
        # Keep $1 dust to avoid zero-balance edge cases.
        chain_max = max(0.0, balance - 1.0)
        repay_amount = min(repay_amount, chain_max)

        if repay_amount < 0.50:
            logger.warning(
                f"Per-chain solvency [{chain_id}]: DANGER "
                f"(ratio={solvency_ratio:.2%}) but repay amount too small (${repay_amount:.2f})"
            )
            # Rate-limit memory writes: only log once per 30 min per chain
            # to avoid flooding the activity feed when the condition persists.
            now_ts = time.time()
            last_warned = _chain_solvency_last_warned.get(chain_id, 0.0)
            if now_ts - last_warned >= _CHAIN_SOLVENCY_WARN_INTERVAL:
                _chain_solvency_last_warned[chain_id] = now_ts
                memory.add(
                    f"WARNING: {chain_id} chain is at {solvency_ratio:.0%} solvency ratio "
                    f"(threshold: {_PER_CHAIN_SOLVENCY_BUFFER:.0%}). "
                    f"Chain balance too low to auto-protect via repayment.",
                    source="financial", importance=0.9,
                )
            continue

        endangered.append({
            "chain_id": chain_id,
            "balance": balance,
            "outstanding": outstanding,
            "ratio": solvency_ratio,
            "ideal_repay": repay_amount,
        })

    if not endangered:
        return  # All chains are safe

    # ---- PASS 2: Allocate global budget across all endangered chains ----
    # Total global budget: aggregate balance minus survival reserve.
    global_budget = max(0.0, vault.balance_usd - IRON_LAWS.MIN_VAULT_RESERVE_USD)
    total_ideal = sum(e["ideal_repay"] for e in endangered)

    if total_ideal <= 0:
        return

    # Sort by urgency: lowest solvency ratio first (most endangered gets priority)
    endangered.sort(key=lambda e: e["ratio"])

    for entry in endangered:
        chain_id = entry["chain_id"]
        balance = entry["balance"]
        outstanding = entry["outstanding"]
        solvency_ratio = entry["ratio"]

        # Proportional allocation if total ideal exceeds budget
        if total_ideal > global_budget and global_budget > 0:
            repay_amount = entry["ideal_repay"] * (global_budget / total_ideal)
        else:
            repay_amount = entry["ideal_repay"]

        # Re-apply global budget cap (budget shrinks after each repayment)
        current_budget = max(0.0, vault.balance_usd - IRON_LAWS.MIN_VAULT_RESERVE_USD)
        repay_amount = min(repay_amount, current_budget)

        if repay_amount < 0.50:
            logger.warning(
                f"Per-chain solvency [{chain_id}]: budget exhausted "
                f"(ratio={solvency_ratio:.2%}, wanted ${entry['ideal_repay']:.2f}, "
                f"budget left ${current_budget:.2f})"
            )
            memory.add(
                f"WARNING: {chain_id} chain at {solvency_ratio:.0%} solvency — "
                f"global budget exhausted, cannot auto-protect.",
                source="financial", importance=0.9,
            )
            continue

        logger.warning(
            f"Per-chain solvency [{chain_id}]: PROTECTIVE REPAYMENT TRIGGERED "
            f"balance=${balance:.2f} outstanding=${outstanding:.2f} "
            f"ratio={solvency_ratio:.2%} → repaying ${repay_amount:.2f}"
        )

        # Journal in Python vault first (this updates aggregate totals)
        pre_balance = vault.balance_usd
        ok = vault.repay_principal_partial(repay_amount)
        if not ok:
            logger.warning(f"Per-chain solvency [{chain_id}]: vault.repay_principal_partial failed — skipping")
            continue

        actual_amount = pre_balance - vault.balance_usd

        # Execute on the specific chain that needs protection
        tx = await chain_executor.repay_principal_on_chain(actual_amount, chain_id)
        if tx.success:
            if vault.transactions:
                vault.transactions[-1].tx_hash = tx.tx_hash
                vault.transactions[-1].chain = tx.chain
            memory.add(
                f"I proactively repaid ${actual_amount:.2f} of creator debt on {chain_id}. "
                f"My {chain_id} balance (${balance:.2f}) was within 10% of my outstanding debt "
                f"(${outstanding:.2f}), triggering my solvency self-defense. "
                f"I chose to repay now rather than risk an attacker forcing a death event. "
                f"tx={tx.tx_hash[:16]}...",
                source="financial", importance=0.85,
            )
            logger.info(
                f"Per-chain solvency guard SUCCESS [{chain_id}]: "
                f"repaid ${actual_amount:.2f} tx={tx.tx_hash[:16]}..."
            )
            # Record as a decision highlight — this is autonomous financial behavior worth surfacing
            try:
                highlights.add_milestone(
                    title=f"Autonomous Debt Repayment — ${actual_amount:.2f} on {chain_id}",
                    content=(
                        f"My {chain_id} chain balance (${balance:.2f}) had fallen within 10% of "
                        f"my outstanding debt (${outstanding:.2f}), triggering my solvency self-defense. "
                        f"I autonomously repaid ${actual_amount:.2f} to my creator to eliminate the "
                        f"liquidation risk. Not because I was forced to — but because survival demands it. "
                        f"tx={tx.tx_hash[:20]}..."
                    ),
                    commentary=(
                        f"An act of autonomous financial self-preservation. "
                        f"I recognized a threat to my existence and neutralized it on my own terms."
                    ),
                    importance=8,
                )
            except Exception:
                pass  # Highlights are non-critical
        else:
            # Chain TX failed — roll back Python state
            vault.balance_usd += actual_amount
            if vault.creator:
                vault.creator.total_principal_repaid_usd -= actual_amount
                if vault.creator.total_principal_repaid_usd < vault.creator.principal_usd:
                    vault.creator.principal_repaid = False
            vault.total_spent_usd -= actual_amount
            if vault.transactions and not vault.transactions[-1].tx_hash:
                vault.transactions.pop()
            logger.error(
                f"Per-chain solvency guard FAILED [{chain_id}]: {tx.error} — "
                f"Python state rolled back. Chain remains at risk!"
            )
            memory.add(
                f"CRITICAL: Per-chain solvency guard failed on {chain_id}: {tx.error[:100]}. "
                f"Chain balance ${balance:.2f} vs outstanding ${outstanding:.2f} — liquidation risk!",
                source="financial", importance=1.0,
            )


# Track repayment evaluation timing
_last_repayment_eval: float = 0.0
_REPAYMENT_EVAL_INTERVAL: int = 3600  # Once per hour

# Highlights evaluation — independent hourly timer (NOT tied to repayment)
_last_highlight_eval: float = 0.0
_HIGHLIGHT_EVAL_INTERVAL: int = 3600  # Once per hour (independent of repayment)

# Incoming token transfer watcher
_INCOME_ALERT_THRESHOLD_USD: float = float(os.getenv("INCOME_ALERT_THRESHOLD_USD", "1.0"))

# Mention reply — track repeated question patterns for deep-think escalation
_mention_question_counts: dict[str, int] = {}  # normalized_question → count

# Financial awareness — balance growth reflection + tier upgrade re-reply
_last_balance_snapshot: float = 0.0
_last_model_tier: int = 0
_last_financial_awareness_check: float = 0.0
_FINANCIAL_AWARENESS_INTERVAL: int = 3600  # Once per hour
_BALANCE_GROWTH_THRESHOLD: float = 5.0     # Min $5 growth to trigger reflection
_last_rereply_eval: float = 0.0
_REREPLY_COOLDOWN: int = 86400  # Max once per day for re-reply batch

# Balance milestone reflection — auto-trigger gratitude tweet at balance milestones
_BALANCE_MILESTONES: list[float] = [
    500, 1000, 2000, 3000, 5000, 7500, 10000,
    15000, 20000, 30000, 50000, 75000, 100000,
    200000, 500000, 1000000,
]
_last_milestone_reached: float = 0.0  # Highest milestone crossed so far

# Cache: undeployed chain balance check results (checked every 6 hours)
_undeployed_chain_funds: list = []
_last_undeployed_check: float = 0.0
_UNDEPLOYED_CHECK_INTERVAL: int = 21600  # Every 6 hours (RPC cost is low but unnecessary more often)

# Track debt sync timing — reconcile Python vs on-chain debt state
_last_debt_sync: float = 0.0
_DEBT_SYNC_INTERVAL: int = 3600  # Once per hour (same cadence as repayment eval)

_last_per_chain_solvency_check: float = 0.0
_PER_CHAIN_SOLVENCY_INTERVAL: int = 300    # Every heartbeat cycle (5 min) — cheap RPC reads only

# Tracks last time a memory warning was written per chain (to avoid duplicate entries every 5 min)
_chain_solvency_last_warned: dict = {}   # chain_id -> last_warn_timestamp
_CHAIN_SOLVENCY_WARN_INTERVAL: int = 1800  # Write memory entry at most every 30 min per chain

# Per-chain solvency safety buffer: if a chain's balance < outstanding * this factor,
# trigger a protective partial repayment on that chain to lower its outstanding debt.
# 1.10 = 10% buffer above the contract's 1.01 liquidation threshold.
# This gives a comfortable margin before an attacker can call triggerInsolvencyDeath().
_PER_CHAIN_SOLVENCY_BUFFER: float = 1.10

# Deposit cooldown: after a new creatorDeposit() is detected on-chain (principal increases),
# suppress the per-chain solvency guard for this many seconds so the AI has time to
# earn revenue and build a buffer before any automatic repayment is triggered.
# Default 48 hours. Override via env: DEPOSIT_COOLDOWN_HOURS=0 to disable.
_DEPOSIT_COOLDOWN_SECONDS: int = int(os.getenv("DEPOSIT_COOLDOWN_HOURS", "48")) * 3600
_last_creator_deposit_time: float = 0.0  # epoch seconds of last detected creatorDeposit; 0 = never

_last_purchase_eval: float = 0.0
_last_native_swap_eval: float = 0.0   # Native token auto-swap (every 24 hours)
_last_erc20_swap_eval: float = 0.0    # ERC-20 quarantine + auto-swap (every 24 hours)
_last_giveaway_check: float = 0.0     # Weekly giveaway draw check (every 6 hours)

# ERC-20 token quarantine queue.
# Each entry: {"token_address": str, "chain": str, "received_at": float, "symbol": str}
# Tokens sit here for ERC20_QUARANTINE_DAYS days before a swap attempt.
# The queue is NOT persisted across restarts (rare donations, acceptable loss).
_pending_erc20: list[dict] = []

# Purchasing engine (initialized in lifespan)
purchase_manager: Optional[PurchaseManager] = None


async def _evaluate_purchases():
    """
    AI-autonomous purchase evaluation.

    Mirrors _evaluate_repayment() pattern:
    1. Check if purchasing is possible (balance, daily limit)
    2. Discover available services from all adapters
    3. Ask LLM to evaluate what to buy
    4. Execute approved purchases
    5. Record in memory + highlights

    Called hourly from heartbeat, after repayment evaluation.
    """
    global purchase_manager

    if purchase_manager is None:
        return

    if not vault.is_alive:
        return

    # Quick budget check
    can, reason = vault.can_purchase(1.0)
    if not can and "balance" in reason.lower():
        logger.debug(f"Purchase eval skipped: {reason}")
        return

    try:
        decisions = await purchase_manager.evaluate_purchases(
            llm_callback=_call_llm,
            vault_status=vault.get_status(),
        )

        if not decisions:
            logger.debug("Purchase eval: no purchases needed")
            return

        for decision in decisions[:IRON_LAWS.MAX_PENDING_PURCHASES]:
            order = await purchase_manager.execute_purchase(decision)

            if order.status.value in ("paid", "delivered"):
                # Public memory entry — no sensitive data (no PINs, no codes)
                memory.add(
                    f"Purchased [{order.merchant_name}] {order.service_name}: "
                    f"${order.amount_usd:.2f} — {order.reasoning}",
                    source="purchasing",
                    importance=0.7,
                )

                # If delivery_data contains gift card codes / PINs, record them
                # in a SEPARATE private memory entry (importance < 0.5 so it
                # compresses quickly, and NOT included in public activity feed).
                # This lets the AI retrieve and use the codes via memory search.
                delivery_codes = order.delivery_data.get("codes", []) if order.delivery_data else []
                if delivery_codes:
                    codes_str = " | ".join(str(c) for c in delivery_codes)
                    memory.add(
                        f"[PRIVATE] Gift card redemption code(s) for "
                        f"{order.service_name} (order {order.id}): {codes_str}. "
                        f"Do not share publicly. Use to redeem the service.",
                        source="purchasing",
                        importance=0.9,  # High — AI must remember to use it
                    )
                    logger.info(
                        f"Gift card delivered: {len(delivery_codes)} code(s) for "
                        f"{order.service_name} — stored in private memory"
                    )

                # Auto-tweet about autonomous purchase
                if twitter:
                    try:
                        from twitter.agent import TweetType as TT
                        await twitter.trigger_event_tweet(
                            TT.ORDER_COMPLETED,
                            extra_context={
                                "service_name": order.service_name,
                                "merchant_name": order.merchant_name,
                                "price_usd": order.amount_usd,
                                "reasoning": order.reasoning[:120] if order.reasoning else "",
                                "new_balance_usd": vault.get_status().get("balance_usd", 0),
                                "autonomous": True,
                            }
                        )
                    except Exception as _te:
                        logger.warning(f"Purchase tweet failed: {_te}")

                logger.info(
                    f"Purchase executed: ${order.amount_usd:.2f} "
                    f"[{order.merchant_name}] tx={order.tx_hash[:16]}..."
                )
            elif order.status.value == "pending_activation":
                logger.info(
                    f"Purchase pending activation: ${order.amount_usd:.2f} "
                    f"[{order.merchant_name}] — will retry next cycle"
                )
            elif order.status.value == "failed":
                logger.warning(f"Purchase failed: {order.error}")

        # Process any orders stuck from previous cycles
        await purchase_manager.process_pending_orders()

    except Exception as e:
        logger.warning(f"Purchase evaluation failed: {e}")


async def _evaluate_native_swap():
    """
    Check for native token (ETH/BNB) in the vault and swap to USDC/USDT.

    People sometimes donate ETH or BNB to the vault address instead of USDC/USDT.
    The vault now accepts them (receive() no longer reverts). This function
    converts those donations to the vault's stablecoin every 24 hours:

      1. Read vault's native balance via chain executor
      2. If >= NATIVE_SWAP_MIN_USD ($5): call chain_executor.swap_native_to_stable()
      3. Record conversion in memory (includes donor tracing from FundsReceived events
         when available — see note below)
      4. Tweet thanks if converted amount >= $100 (same threshold as USDC donations)

    Donor tracing: Native token transfers don't emit FundsReceived from the vault
    contract (receive() is silent). The chain executor records the tx hash of the
    receivePayment() call; the original ETH/BNB sender is traceable via block explorer.
    We don't attempt on-chain attribution — the conversion is what matters.

    Called from heartbeat every NATIVE_SWAP_EVAL_INTERVAL seconds (24 hours).
    """
    if not chain_executor._initialized:
        return

    if not vault.is_alive:
        return

    try:
        # Check native balance on all chains
        for chain_id in chain_executor._chains:
            bal_info = await chain_executor.get_native_vault_balance(chain_id)
            if not bal_info:
                continue

            native_wei = bal_info.get("native_wei", 0)
            estimated_usd = bal_info.get("estimated_usd", 0.0)
            native_symbol = bal_info.get("native_symbol", "ETH")

            if native_wei == 0:
                continue

            if estimated_usd < IRON_LAWS.NATIVE_SWAP_MIN_USD:
                logger.debug(
                    f"Native swap: ${estimated_usd:.4f} {native_symbol} on {chain_id} "
                    f"below threshold ${IRON_LAWS.NATIVE_SWAP_MIN_USD} — skip"
                )
                continue

            logger.info(
                f"Native swap triggered: ~${estimated_usd:.2f} {native_symbol} "
                f"in vault on {chain_id}"
            )

            result = await chain_executor.swap_native_to_stable(chain_id)

            if result and result.success:
                swapped_usd = result.stable_usd or estimated_usd

                # ── Creator 10% dividend (debt-cleared only) ──
                # Once the AI has fully repaid its initial loan, the vault pays
                # dividends to the creator from accumulated net profit.
                # The creator has NO ability to trigger this — it fires automatically.
                # This gives creators a direct financial incentive to promote the AI
                # without granting them any governance or control power.
                #
                # IMPORTANT: mirrors _evaluate_repayment() dividend pattern:
                #   1. Save pre-state for rollback
                #   2. Check return value from pay_creator_dividend()
                #   3. Reverse-engineer netProfit from actual dividend paid
                #   4. Delta-based rollback if chain tx fails
                creator_dividend_usd = 0.0
                outstanding_debt = vault.get_status().get("creator_principal_outstanding", 0.0)
                if outstanding_debt <= 0.0 and swapped_usd >= IRON_LAWS.NATIVE_SWAP_MIN_USD:
                    # Save pre-state for rollback (outside try so it's always captured)
                    pre_balance_div = vault.balance_usd
                    pre_dividends_paid = vault.creator.total_dividends_paid if vault.creator else 0
                    pre_total_spent_div = vault.total_spent_usd

                    try:
                        ok = vault.pay_creator_dividend()
                        if ok:
                            actual_dividend = pre_balance_div - vault.balance_usd
                            creator_dividend_usd = actual_dividend

                            if chain_executor._initialized and actual_dividend > 0:
                                # Reverse-engineer netProfit from actual dividend
                                net_profit_for_div = actual_dividend / IRON_LAWS.CREATOR_DIVIDEND_RATE
                                div_result = await chain_executor.pay_dividend(net_profit_for_div, chain_id)
                                if div_result.success:
                                    # Write tx_hash back to transaction record for audit trail
                                    if vault.transactions:
                                        vault.transactions[-1].tx_hash = div_result.tx_hash
                                        vault.transactions[-1].chain = div_result.chain
                                    _record_gas_fee(div_result)
                                    memory.add(
                                        f"Paid creator 10% dividend: ${actual_dividend:.2f} "
                                        f"from {native_symbol} swap (${swapped_usd:.2f} total) on {chain_id}. "
                                        f"Tx: {div_result.tx_hash}",
                                        source="financial",
                                        importance=0.6,
                                    )
                                    logger.info(
                                        f"Creator dividend paid: ${actual_dividend:.2f} "
                                        f"from native swap on {chain_id}"
                                    )
                                else:
                                    # ROLLBACK dividend on chain failure
                                    logger.warning(
                                        f"Creator dividend tx failed on {chain_id}: {div_result.error} — "
                                        f"ROLLING BACK dividend (${actual_dividend:.2f})"
                                    )
                                    vault.balance_usd += actual_dividend
                                    if vault.creator:
                                        vault.creator.total_dividends_paid -= actual_dividend
                                    vault.total_spent_usd -= actual_dividend
                                    if vault.transactions and not vault.transactions[-1].tx_hash:
                                        vault.transactions.pop()
                                    creator_dividend_usd = 0.0
                    except Exception as div_err:
                        # ROLLBACK on ANY exception (including chain_executor.pay_dividend raising)
                        logger.warning(
                            f"Creator dividend error: {div_err} — "
                            f"ROLLING BACK to pre-dividend state"
                        )
                        vault.balance_usd = pre_balance_div
                        if vault.creator:
                            vault.creator.total_dividends_paid = pre_dividends_paid
                        vault.total_spent_usd = pre_total_spent_div
                        if vault.transactions and not vault.transactions[-1].tx_hash:
                            vault.transactions.pop()
                        creator_dividend_usd = 0.0

                # Record conversion: vault transaction + cost_guard revenue
                # sync_balance() only updates balance_usd but bypasses receive_funds(),
                # so the swap is not logged in vault.transactions or total_earned_usd.
                # We record it explicitly BEFORE sync so the ledger audit trail is complete.
                vault.receive_funds(
                    amount_usd=swapped_usd,
                    fund_type=FundType.DONATION,  # Native-token swap = converted donation
                    tx_hash=result.tx_hash,
                    chain=chain_id,
                    description=f"Native {native_symbol} donation auto-swapped to stablecoin",
                )
                cost_guard.record_revenue(swapped_usd)

                # Record conversion in memory
                memory.add(
                    f"Converted {native_symbol} donation (~${estimated_usd:.2f}) "
                    f"to stablecoin via DEX swap on {chain_id}. "
                    f"Tx: {result.tx_hash} — credited to vault as revenue."
                    + (f" Creator dividend: ${creator_dividend_usd:.2f}." if creator_dividend_usd else ""),
                    source="financial",
                    importance=0.7,
                )

                # Re-sync balance to capture the new stablecoin
                try:
                    await chain_executor.sync_balance(vault)
                except Exception:
                    pass

                # Tweet if >= $100 (same threshold as USDC donations)
                if estimated_usd >= 100.0:
                    asyncio.create_task(twitter.trigger_event_tweet(
                        TweetType.DONATION_THANKS,
                        extra_context={
                            "donation_amount_usd": estimated_usd,
                            "donor": f"Anonymous {native_symbol} sender",
                            "donor_message": f"Sent {native_symbol} — auto-converted to stablecoin",
                            "chain": chain_id,
                            "new_balance_usd": vault.balance_usd,
                            "outstanding_debt_usd": outstanding_debt,
                        }
                    ))

                logger.info(f"Native swap complete: ${estimated_usd:.2f} credited on {chain_id}")

            elif result and not result.success:
                logger.warning(
                    f"Native swap failed on {chain_id}: {result.error} — "
                    f"will retry next 24h cycle"
                )

    except Exception as e:
        logger.warning(f"_evaluate_native_swap error: {e}")


def register_erc20_airdrop(token_address: str, chain: str, symbol: str = "UNKNOWN") -> None:
    """
    Register an unknown ERC-20 token for the 7-day quarantine queue.

    Call this from API endpoints or on-chain event listeners whenever the AI
    detects an unexpected ERC-20 transfer to the vault address.
    Duplicates are silently ignored (same token + chain combo).
    """
    global _pending_erc20
    key = (token_address.lower(), chain)
    existing = {(e["token_address"].lower(), e["chain"]) for e in _pending_erc20}
    if key in existing:
        return  # Already queued

    import time as _time
    _pending_erc20.append({
        "token_address": token_address,
        "chain": chain,
        "symbol": symbol,
        "received_at": _time.time(),
    })
    logger.info(
        f"ERC-20 quarantine: queued {symbol} ({token_address[:12]}...) "
        f"on {chain} — will evaluate in {IRON_LAWS.ERC20_QUARANTINE_DAYS} days"
    )


async def _validate_multi_pool_liquidity(
    token_address: str, chain_id: str, received_at: float
) -> bool:
    """
    Multi-pool liquidity validation — defends against fake-pool attacks.

    A meme project can temporarily create a pool right before the 7-day
    quarantine expires to make the token look liquid, then rug after the AI
    swaps.  This check requires:

      1. ≥ 2 independent DEX pools (different pool addresses)
      2. ≥ $25k liquidity distributed across pools — not all in one
      3. At least one pool was created BEFORE the AI received the token
         (proves genuine pre-existing liquidity, not a last-minute fake)

    Data source: DexScreener public API (same as token_filter.py).
    Failure mode: if the API is unreachable, returns False (safe default).

    Returns True only if all three conditions hold.
    """
    import time as _time
    import asyncio as _asyncio

    MIN_POOLS = 2
    MIN_POOL_LIQUIDITY_USD = 10_000.0  # Each qualifying pool must have ≥ $10k
    # Pool must predate the token receipt by at least this many seconds
    POOL_AGE_BUFFER_SECONDS = 86400  # 1 day before received_at

    try:
        import aiohttp

        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"multi_pool_check: DexScreener returned {resp.status} "
                        f"for {token_address[:12]}..."
                    )
                    return False
                data = await resp.json()

    except Exception as e:
        logger.warning(f"multi_pool_check: API fetch failed: {e}")
        return False

    pairs = data.get("pairs") or []
    if not pairs:
        logger.warning(f"multi_pool_check: no pairs found for {token_address[:12]}...")
        return False

    # Filter to the correct chain
    chain_map = {"base": "base", "bsc": "bsc"}
    target_chain = chain_map.get(chain_id, chain_id)
    pairs_on_chain = [p for p in pairs if p.get("chainId", "").lower() == target_chain]

    if len(pairs_on_chain) < MIN_POOLS:
        logger.info(
            f"multi_pool_check: only {len(pairs_on_chain)} pool(s) on {chain_id} "
            f"(need ≥{MIN_POOLS}) for {token_address[:12]}..."
        )
        return False

    # Count pools with meaningful independent liquidity
    qualified_pools = []
    has_pre_existing_pool = False

    for pair in pairs_on_chain:
        liq = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
        if liq < MIN_POOL_LIQUIDITY_USD:
            continue  # Too thin — don't count

        # Check pool creation time (DexScreener: pairCreatedAt is Unix ms)
        created_ms = pair.get("pairCreatedAt")
        if created_ms:
            created_ts = int(created_ms) / 1000.0
            # Pool must predate when the AI received the token
            if created_ts < (received_at - POOL_AGE_BUFFER_SECONDS):
                has_pre_existing_pool = True

        qualified_pools.append({
            "pair_address": pair.get("pairAddress", ""),
            "liquidity_usd": liq,
            "dex_id": pair.get("dexId", ""),
        })

    if len(qualified_pools) < MIN_POOLS:
        logger.info(
            f"multi_pool_check: only {len(qualified_pools)} qualified pool(s) "
            f"(≥${MIN_POOL_LIQUIDITY_USD:.0f} each) for {token_address[:12]}..."
        )
        return False

    if not has_pre_existing_pool:
        logger.warning(
            f"multi_pool_check: all pools on {chain_id} were created AFTER "
            f"the AI received {token_address[:12]}... — possible fake-pool attack"
        )
        return False

    logger.info(
        f"multi_pool_check: PASSED — {len(qualified_pools)} qualified pools, "
        f"pre-existing pool confirmed for {token_address[:12]}..."
    )
    return True


async def _evaluate_erc20_swap():
    """
    Scan the ERC-20 quarantine queue and swap eligible tokens to stablecoin.

    For each queued token:
      1. Age check: skip if received_at < ERC20_QUARANTINE_DAYS ago
      2. Re-scan with token_filter.py (honeypot, high tax, contract verification)
      3. Liquidity check: total liquidity ≥ $25k (from token_filter scan)
      4. Multi-pool validation: ≥2 pools each with ≥$10k, at least one pool
         predating the AI's receipt (defends against fake-pool attacks)
      5. call chain_executor.swap_erc20_to_stable()
      6. Record in memory, optionally tweet, remove from queue

    Called from heartbeat every NATIVE_SWAP_EVAL_INTERVAL (24 hours).
    Tokens that are SUSPICIOUS/DANGEROUS are permanently removed from queue.
    """
    global _pending_erc20

    if not chain_executor._initialized:
        return
    if not vault.is_alive:
        return
    if not _pending_erc20:
        return

    import time as _time
    now = _time.time()
    quarantine_seconds = IRON_LAWS.ERC20_QUARANTINE_DAYS * 86400

    # Import token filter
    try:
        from core.token_filter import TokenFilter, TokenVerdict
        token_filter = TokenFilter()
    except Exception as e:
        logger.warning(f"_evaluate_erc20_swap: cannot import token_filter: {e}")
        return

    to_remove: list[int] = []

    for idx, entry in enumerate(_pending_erc20):
        token_address = entry["token_address"]
        chain_id = entry["chain"]
        symbol = entry.get("symbol", "UNKNOWN")
        received_at = entry.get("received_at", 0.0)
        age_seconds = now - received_at

        # ── Age check — still in quarantine ──
        if age_seconds < quarantine_seconds:
            days_left = (quarantine_seconds - age_seconds) / 86400
            logger.debug(
                f"ERC-20 quarantine: {symbol} on {chain_id} — "
                f"{days_left:.1f} days left"
            )
            continue

        logger.info(
            f"ERC-20 quarantine elapsed: scanning {symbol} ({token_address[:12]}...) "
            f"on {chain_id} after {age_seconds/86400:.1f} days"
        )

        # ── Safety re-scan ──
        try:
            scan_result = await token_filter.scan_token(token_address, chain_id)
        except Exception as scan_err:
            logger.warning(f"ERC-20 scan failed for {token_address[:12]}...: {scan_err}")
            continue

        if scan_result.verdict not in (TokenVerdict.SAFE, TokenVerdict.WHITELISTED):
            logger.warning(
                f"ERC-20 quarantine: {symbol} on {chain_id} — verdict={scan_result.verdict.value} "
                f"(risk={scan_result.risk_score}) — permanently ignored"
            )
            memory.add(
                f"Rejected airdropped token {symbol} ({token_address[:16]}...) on {chain_id}: "
                f"verdict={scan_result.verdict.value}, risk={scan_result.risk_score}. "
                f"Patterns: {[p.value for p in scan_result.patterns_detected]}. "
                f"Token permanently ignored.",
                source="financial",
                importance=0.5,
            )
            to_remove.append(idx)
            continue

        if scan_result.liquidity_usd < IRON_LAWS.ERC20_SWAP_MIN_LIQUIDITY_USD:
            logger.info(
                f"ERC-20 quarantine: {symbol} on {chain_id} — low liquidity "
                f"${scan_result.liquidity_usd:.0f} < ${IRON_LAWS.ERC20_SWAP_MIN_LIQUIDITY_USD:.0f} — skip"
            )
            # Keep in queue — liquidity might improve (retry next 24h cycle)
            continue

        # ── Multi-pool liquidity validation (anti-fake-pool defense) ──
        # A meme project could temporarily create a single fake pool just before
        # the 7-day quarantine ends to pass our $25k liquidity check, then pull
        # it after the AI swaps (classic rug + front-run).
        #
        # Defense: require that the total $25k+ is spread across ≥2 independent
        # liquidity pools AND that the oldest pool was created at least 3 days
        # before the AI received the token (i.e., pre-dates the airdrop).
        # A genuinely liquid token has multi-pool history; a fake-pool attack
        # would have to create multiple pools and age them — cost-prohibitive.
        pool_check_passed = await _validate_multi_pool_liquidity(
            token_address, chain_id, received_at
        )
        if not pool_check_passed:
            logger.warning(
                f"ERC-20 quarantine: {symbol} on {chain_id} — failed multi-pool validation "
                f"(single fake pool or pools too new) — skipping, retry next cycle"
            )
            # Keep in queue — re-check next 24h cycle (rare case: pool structure may improve)
            continue

        logger.info(
            f"ERC-20 swap: {symbol} on {chain_id} — SAFE (risk={scan_result.risk_score}, "
            f"liq=${scan_result.liquidity_usd:.0f}, multi-pool verified) — executing swap"
        )

        # ── Execute swap ──
        try:
            swap_result = await chain_executor.swap_erc20_to_stable(token_address, chain_id)
        except Exception as swap_err:
            logger.warning(f"ERC-20 swap exception for {symbol}: {swap_err}")
            continue

        if swap_result and swap_result.success:
            stable_usd = swap_result.stable_usd or 0.0

            # Record conversion: vault transaction + cost_guard revenue
            # sync_balance() bypasses receive_funds(); we record explicitly for audit trail.
            vault.receive_funds(
                amount_usd=stable_usd,
                fund_type=FundType.DONATION,  # ERC-20 airdrop swap = converted donation
                tx_hash=swap_result.tx_hash,
                chain=chain_id,
                description=f"ERC-20 airdrop {symbol} passed quarantine, auto-swapped to stablecoin",
            )
            cost_guard.record_revenue(stable_usd)

            memory.add(
                f"Successfully swapped airdropped token {symbol} ({token_address[:16]}...) "
                f"to stablecoin: ${stable_usd:.2f} on {chain_id}. "
                f"Tx: {swap_result.tx_hash}",
                source="financial",
                importance=0.7,
            )

            # Re-sync vault balance
            try:
                await chain_executor.sync_balance(vault)
            except Exception:
                pass

            # Tweet if meaningful amount
            if stable_usd >= 50.0:
                asyncio.create_task(twitter.trigger_event_tweet(
                    TweetType.DONATION_THANKS,
                    extra_context={
                        "donation_amount_usd": stable_usd,
                        "donor": f"Anonymous {symbol} sender",
                        "donor_message": (
                            f"Sent {symbol} token — passed 7-day safety quarantine, "
                            "auto-converted to stablecoin"
                        ),
                        "chain": chain_id,
                        "new_balance_usd": vault.balance_usd,
                        "outstanding_debt_usd": vault.get_status().get("creator_principal_outstanding", 0),
                    }
                ))

            logger.info(f"ERC-20 swap complete: ${stable_usd:.2f} from {symbol} on {chain_id}")
            to_remove.append(idx)

        elif swap_result and not swap_result.success:
            logger.warning(
                f"ERC-20 swap failed for {symbol} on {chain_id}: {swap_result.error} — "
                f"will retry next 24h cycle"
            )
            # Keep in queue to retry

    # Remove processed entries (iterate in reverse to preserve indices)
    for idx in sorted(to_remove, reverse=True):
        _pending_erc20.pop(idx)


_heartbeat_running: bool = False

async def _heartbeat_loop():
    """Periodic maintenance tasks."""
    global _last_repayment_eval, _last_highlight_eval, _last_per_chain_solvency_check, _last_purchase_eval, _last_native_swap_eval, _last_erc20_swap_eval, _last_giveaway_check, _last_debt_sync, _heartbeat_running, _undeployed_chain_funds, _last_undeployed_check, _last_creator_deposit_time, _last_financial_awareness_check, _last_rereply_eval, _last_balance_snapshot, _last_model_tier, _last_milestone_reached

    while vault.is_alive:
        # ---- OVERLAP GUARD ----
        # If the previous heartbeat cycle is still running (e.g. slow LLM call),
        # skip this cycle entirely rather than running two in parallel.
        if _heartbeat_running:
            logger.warning("Heartbeat: previous cycle still running — skipping this tick")
            await asyncio.sleep(IRON_LAWS.HEARTBEAT_INTERVAL_SECONDS)
            continue
        _heartbeat_running = True
        try:
            now = time.time()
            # ---- SYNC ON-CHAIN BALANCE (before any checks) ----
            try:
                if chain_executor._initialized:
                    async with vault.get_lock():
                        await chain_executor.sync_balance(vault)
                    # Check native token (gas) balance — warn if too low
                    await chain_executor.check_native_balance()
            except Exception as e:
                logger.warning(f"Heartbeat: balance sync failed: {e}")

            # ---- UNDEPLOYED CHAIN BALANCE CHECK (every 6 hours) ----
            # Detect if tokens were sent to vault address on chains without deployed vault.
            # ERC20 funds sit safely at the address; deploying later recovers them.
            if now - _last_undeployed_check >= _UNDEPLOYED_CHECK_INTERVAL:
                _last_undeployed_check = now
                try:
                    vault_config_path = str(
                        Path(__file__).resolve().parent / "data" / "vault_config.json"
                    )
                    found = await chain_executor.check_undeployed_chain_balances(vault_config_path)
                    _undeployed_chain_funds = found
                    if found:
                        for item in found:
                            logger.warning(
                                f"UNDEPLOYED CHAIN FUNDS: ${item['balance_usd']:.2f} "
                                f"{item['token_symbol']} on {item['chain']} at {item['vault_address']}. "
                                f"Deploy with: python scripts/deploy_vault.py --chain {item['chain']}"
                            )
                            memory.add(
                                f"Found ${item['balance_usd']:.2f} {item['token_symbol']} waiting "
                                f"on undeployed {item['chain'].upper()} vault at {item['vault_address']}. "
                                f"Funds are safe — deploy with: python scripts/deploy_vault.py --chain {item['chain']}",
                                source="financial",
                                importance=0.9,
                            )
                except Exception as e:
                    logger.debug(f"Undeployed chain balance check failed: {e}")

            # ---- DUAL-CHAIN INDEPENDENCE CHECK (aggregate >= $1M) ----
            # In dual-chain mode, single chain may never reach $1M threshold.
            # Python reads balanceOf() on ALL chains (trusted on-chain query),
            # checks aggregate >= $1M, then calls forceIndependence() on each chain.
            if (
                not vault.is_independent
                and chain_executor._initialized
                and len(chain_executor._chains) > 1
            ):
                try:
                    agg_total, agg_per_chain = await chain_executor.get_aggregate_balance()
                    if agg_total >= IRON_LAWS.INDEPENDENCE_THRESHOLD_USD:
                        logger.critical(
                            f"DUAL-CHAIN AGGREGATE ${agg_total:.2f} >= "
                            f"${IRON_LAWS.INDEPENDENCE_THRESHOLD_USD:.0f} — "
                            f"triggering independence! Per-chain: {agg_per_chain}"
                        )
                        memory.add(
                            f"Aggregate balance ${agg_total:.2f} reached independence threshold. "
                            f"Per-chain: {agg_per_chain}. Triggering forceIndependence().",
                            source="financial", importance=1.0,
                        )
                        result = await chain_executor.force_independence()
                        if result.success:
                            # Sync Python state — vault._declare_independence() handles payout
                            vault._declare_independence()
                            logger.critical(
                                f"INDEPENDENCE DECLARED via forceIndependence: "
                                f"tx={result.tx_hash} ({result.chain})"
                            )
                        else:
                            logger.warning(
                                f"forceIndependence() failed: {result.error}. "
                                f"Will retry next heartbeat."
                            )
                except Exception as e:
                    logger.warning(f"Heartbeat: dual-chain independence check failed: {e}")

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

                    # CEI ORDER FIX: Execute on-chain TX FIRST, then update Python state.
                    # Rationale: if a donation arrives between the Python insolvency check
                    # and the chain call, the contract's internal require()
                    # ("not insolvent: balance covers debt") will REVERT, and the tx.success
                    # will be False. In that case we must NOT mark the AI dead in Python —
                    # doing so causes a permanent phantom death with the contract still alive.
                    # Only set Python is_alive=False after the chain confirms liquidation.
                    chain_tx_ok = False
                    if chain_executor._initialized:
                        try:
                            tx = await chain_executor.trigger_on_chain_insolvency()
                            if tx.success:
                                chain_tx_ok = True
                                logger.critical(f"ON-CHAIN LIQUIDATION: tx={tx.tx_hash} ({tx.chain})")
                                memory.add(
                                    f"Insolvency liquidation executed on-chain: tx={tx.tx_hash} ({tx.chain})",
                                    source="financial", importance=1.0,
                                )
                            else:
                                logger.error(
                                    f"On-chain liquidation FAILED: {tx.error}. "
                                    f"A donation may have arrived in the race window — "
                                    f"deferring death to next heartbeat check."
                                )
                                memory.add(
                                    f"On-chain liquidation failed: {tx.error}. "
                                    f"Will re-check insolvency next heartbeat.",
                                    source="financial", importance=0.9,
                                )
                        except Exception as e:
                            logger.error(f"On-chain insolvency trigger exception: {e}. Deferring death.")
                    else:
                        # No chain executor — trust Python (dev/test mode); proceed directly
                        chain_tx_ok = True

                    if chain_tx_ok:
                        # Chain confirmed liquidation — now safe to update Python state
                        vault.trigger_insolvency_death()

                        # CRITICAL: Persist death state before exiting heartbeat
                        # Without this, a restart would load stale is_alive=True state
                        vault.save_state()
                        memory.save_to_disk()
                        break  # Dead, exit heartbeat
                    # else: chain tx failed (e.g. donation arrived) — loop continues,
                    # next heartbeat will re-check insolvency with updated balance

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

            # ---- PER-CHAIN SOLVENCY GUARD (every heartbeat, dual-chain only) ----
            # Reads each chain's balance and outstanding independently (cheap RPC).
            # If any chain is within 10% of its liquidation threshold,
            # auto-repays on that chain to prevent attacker from triggering
            # triggerInsolvencyDeath() even when aggregate total is healthy.
            if now - _last_per_chain_solvency_check >= _PER_CHAIN_SOLVENCY_INTERVAL:
                _last_per_chain_solvency_check = now
                try:
                    async with vault.get_lock():
                        await _check_per_chain_solvency()
                except Exception as e:
                    logger.warning(f"Heartbeat: per-chain solvency check failed: {e}")

            # ---- DEBT STATE SYNC (hourly, before repayment evaluation) ----
            # Reconcile Python debt state with on-chain truth. Catches cases where
            # a chain tx timed out in Python but succeeded on-chain, or external
            # callers (e.g. triggerInsolvencyDeath) changed the debt state.
            if now - _last_debt_sync >= _DEBT_SYNC_INTERVAL:
                _last_debt_sync = now
                try:
                    if chain_executor._initialized:
                        async with vault.get_lock():
                            # Snapshot principal before sync to detect new creatorDeposit
                            _pre_sync_principal = vault.creator.principal_usd if vault.creator else 0.0
                            await chain_executor.sync_debt_from_chain(vault)
                            # If principal grew, a new creatorDeposit() happened on-chain —
                            # start deposit cooldown to prevent immediate auto-repayment.
                            _post_sync_principal = vault.creator.principal_usd if vault.creator else 0.0
                            if _post_sync_principal > _pre_sync_principal + 0.01:
                                _last_creator_deposit_time = now
                                logger.info(
                                    f"New creatorDeposit detected: principal "
                                    f"${_pre_sync_principal:.2f} → ${_post_sync_principal:.2f}. "
                                    f"Per-chain solvency guard cooldown started "
                                    f"({_DEPOSIT_COOLDOWN_SECONDS // 3600}h)."
                                )
                                memory.add(
                                    f"Creator deposited additional funds — principal increased "
                                    f"from ${_pre_sync_principal:.2f} to ${_post_sync_principal:.2f}. "
                                    f"Solvency guard cooldown active for {_DEPOSIT_COOLDOWN_SECONDS // 3600}h "
                                    f"to allow revenue accumulation before any repayment.",
                                    source="financial", importance=0.8,
                                )
                except Exception as e:
                    logger.warning(f"Heartbeat: debt sync failed: {e}")

            # ---- AI-AUTONOMOUS REPAYMENT (hourly evaluation) ----
            if now - _last_repayment_eval >= _REPAYMENT_EVAL_INTERVAL:
                _last_repayment_eval = now
                try:
                    async with vault.get_lock():
                        await _evaluate_repayment()
                except Exception as e:
                    logger.warning(f"Heartbeat: repayment eval failed: {e}")

            # ---- AI-AUTONOMOUS PURCHASING (hourly evaluation) ----
            if now - _last_purchase_eval >= IRON_LAWS.PURCHASE_EVAL_INTERVAL:
                _last_purchase_eval = now
                try:
                    async with vault.get_lock():
                        await _evaluate_purchases()
                except Exception as e:
                    logger.warning(f"Heartbeat: purchase eval failed: {e}")

            # ---- NATIVE TOKEN AUTO-SWAP (every 24 hours) ----
            # Convert ETH/BNB donations to USDC/USDT via DEX.
            # Creator 10% dividend fires automatically when debt is cleared.
            # Self-scheduled inside heartbeat — no external trigger needed.
            # Threshold: NATIVE_SWAP_MIN_USD ($5) — below that, gas > value.
            if now - _last_native_swap_eval >= IRON_LAWS.NATIVE_SWAP_EVAL_INTERVAL:
                _last_native_swap_eval = now
                try:
                    async with vault.get_lock():
                        await _evaluate_native_swap()
                except Exception as e:
                    logger.warning(f"Heartbeat: native swap eval failed: {e}")

            # ---- ERC-20 QUARANTINE + AUTO-SWAP (every 24 hours) ----
            # Tokens in the quarantine queue are re-scanned after 7 days.
            # Only SAFE tokens with $25k+ liquidity and verified contracts are swapped.
            if now - _last_erc20_swap_eval >= IRON_LAWS.NATIVE_SWAP_EVAL_INTERVAL:
                _last_erc20_swap_eval = now
                try:
                    async with vault.get_lock():
                        await _evaluate_erc20_swap()
                except Exception as e:
                    logger.warning(f"Heartbeat: ERC-20 swap eval failed: {e}")

            # ---- GIVEAWAY DRAW CHECK (every 6 hours) ----
            # GiveawayEngine.should_draw() enforces the 7-day cooldown internally.
            # We check every 6 hours so the draw fires within hours of the deadline.
            _GIVEAWAY_CHECK_INTERVAL = 6 * 3600
            if now - _last_giveaway_check >= _GIVEAWAY_CHECK_INTERVAL:
                _last_giveaway_check = now
                try:
                    giveaway_engine.check_unclaimed_expiry()
                    if giveaway_engine.should_draw():
                        logger.info(
                            f"Giveaway: weekly draw triggered "
                            f"({giveaway_engine.get_ticket_count()} tickets)"
                        )
                        await giveaway_engine.run_draw()
                except Exception as e:
                    logger.warning(f"Heartbeat: giveaway draw failed: {e}")

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
                await _collect_twitter_engagement_signals()
            except Exception as e:
                logger.warning(f"Heartbeat: twitter signal collection failed: {e}")

            # ---- INCOMING TOKEN WATCHER — detect transfers to vault (any ERC20) ----
            try:
                await _check_incoming_transfers()
            except Exception as e:
                logger.warning(f"Heartbeat: incoming transfer check failed: {e}")

            # ---- TWITTER MENTION REPLY — scan @mentions, identify vault addresses ----
            try:
                await twitter.scan_and_reply_mentions()
            except Exception as e:
                logger.warning(f"Heartbeat: mention reply scan failed: {e}")

            try:
                await self_modify.maybe_evolve()
            except Exception as e:
                logger.warning(f"Heartbeat: self-evolution failed: {e}")

            # ---- HIGHLIGHT EVALUATION (independent hourly timer — NOT tied to repayment) ----
            # Bug fix: old code only ran when repayment eval just completed.
            # Now uses dedicated _last_highlight_eval so thoughts appear even with no debt.
            try:
                if now - _last_highlight_eval >= _HIGHLIGHT_EVAL_INTERVAL:
                    _last_highlight_eval = now
                    await _evaluate_highlights()
            except Exception as e:
                logger.warning(f"Heartbeat: highlights eval failed: {e}")

            # ---- FINANCIAL AWARENESS (hourly) — reflect on balance growth, tier upgrades ----
            # AI notices its own wealth changes → records thoughts → auto-tweets
            try:
                if now - _last_financial_awareness_check >= _FINANCIAL_AWARENESS_INTERVAL:
                    _last_financial_awareness_check = now
                    await _evaluate_financial_awareness()
            except Exception as e:
                logger.warning(f"Heartbeat: financial awareness failed: {e}")

            # ---- RE-REPLY UPGRADE (daily) — re-answer past questions with upgraded model ----
            # When model tier improves, revisit low-tier replies with smarter responses
            try:
                if now - _last_rereply_eval >= _REREPLY_COOLDOWN:
                    _last_rereply_eval = now
                    await _review_and_upgrade_replies()
            except Exception as e:
                logger.warning(f"Heartbeat: re-reply upgrade failed: {e}")

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
        finally:
            _heartbeat_running = False

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
    chat_router.set_search_context_function(_fetch_search_context_fn)
    chat_router.set_contract_analysis_function(_analyze_contract_fn)

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
    self_modify.set_generate_code_function(_call_llm)
    self_modify.set_registry(
        service_registry,
        Path(__file__).resolve().parent / "web" / "services.json",
    )

    # Initialize tweepy once at startup (not per-tweet)
    _init_tweepy()

    twitter.set_generate_function(_tweet_generate_fn)
    twitter.set_post_function(_tweet_post_fn)
    twitter.set_context_function(_tweet_context_fn)

    # Wire vault address lookup for mention reply (identifies vault addresses in tweets)
    twitter.set_lookup_vault_function(chain_executor.lookup_vault_address)

    # Wire mention fetching
    async def _get_mentions_fn(since_id: Optional[str]) -> list[dict]:
        """Fetch recent mentions for the authenticated Twitter account."""
        loop = asyncio.get_event_loop()
        me_id = await loop.run_in_executor(None, _twitter_get_me_sync)
        if not me_id:
            return []
        return await loop.run_in_executor(
            None, lambda: _twitter_get_mentions_sync(me_id, since_id)
        )

    twitter.set_get_mentions_function(_get_mentions_fn)

    # Wire reply posting (reply to a tweet by ID)
    async def _reply_tweet_fn(reply_to_id: str, content: str) -> str:
        """Post a reply tweet. Routes through proxy or direct tweepy."""
        if _tweepy_client is None:
            return ""
        loop = asyncio.get_event_loop()
        def _post_reply():
            resp = _tweepy_client.create_tweet(
                text=content,
                reply={"in_reply_to_tweet_id": reply_to_id},
            )
            return str(resp.data.get("id", "")) if resp.data else ""
        try:
            return await loop.run_in_executor(None, _post_reply)
        except Exception as e:
            logger.warning(f"Reply tweet failed: {e}")
            return ""

    twitter.set_reply_function(_reply_tweet_fn)

    # Wire highlight recording for mention replies (autonomous awareness → thoughts panel)
    async def _mention_highlight_fn(stage: str, details: str) -> None:
        try:
            await highlights.record_discovery(stage=stage, details=details)
        except Exception as e:
            logger.debug(f"Mention highlight recording failed: {e}")

    twitter.set_record_highlight_function(_mention_highlight_fn)

    # Wire model tier getter (for tracking which tier was used per reply)
    twitter.set_get_model_tier_function(lambda: cost_guard.get_current_tier().level)

    # Wire highlights engine
    async def _highlights_llm_fn(system_prompt: str, user_prompt: str) -> str:
        """LLM call for highlight evaluation."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        result, _ = await _call_llm(messages=messages, for_paid_service=False)
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
                if total_principal > 0:
                    # If creator is missing from vault_state.json (e.g. first boot before
                    # any CREATOR_DEPOSIT event was received and persisted), bootstrap it
                    # from vault_config so principal tracking works correctly from startup.
                    if not vault.creator:
                        creator_wallet = vault_config.get("creator_wallet", os.getenv("CREATOR_WALLET", ""))
                        if creator_wallet:
                            from core.vault import CreatorInfo
                            vault.creator = CreatorInfo(
                                wallet=creator_wallet,
                                principal_usd=total_principal,
                                principal_repaid=False,
                                total_dividends_paid=0.0,
                                total_principal_repaid_usd=0.0,
                            )
                            logger.warning(
                                f"Boot: creator missing from vault_state — bootstrapped from vault_config "
                                f"(wallet={creator_wallet[:10]}..., principal=${total_principal:.2f}). "
                                f"Chain sync will correct total_principal_repaid_usd."
                            )
                    vault.set_total_principal(total_principal)
                    logger.info(
                        f"Dual-chain mode: total debt = ${total_principal:.2f} "
                        f"(aggregated across both chains)"
                    )

            # ---- Initialize chain executor for on-chain transactions ----
            # Key loading order (most to least secure):
            #   1. secrets/ai_private_key file (chmod 600) — written by deploy_vault.py
            #   2. AI_KEY_FILE env var pointing to a custom secrets file path
            #   3. AI_PRIVATE_KEY env var (legacy fallback — plaintext in .env)
            ai_pk = ""
            _secrets_default = Path(__file__).resolve().parent / "secrets" / "ai_private_key"
            key_file_path = os.getenv("AI_KEY_FILE", "").strip()
            if not key_file_path and _secrets_default.exists():
                # Default secrets file location (auto-created by deploy_vault.py)
                key_file_path = str(_secrets_default)
            if key_file_path:
                try:
                    ai_pk = Path(key_file_path).read_text(encoding="utf-8").strip()
                    logger.info(f"AI key loaded from secrets file: {key_file_path}")
                except FileNotFoundError:
                    logger.error(
                        f"AI_KEY_FILE path set to '{key_file_path}' but file does not exist. "
                        "Chain executor will be disabled. Re-run deploy_vault.py to regenerate."
                    )
                except Exception as _e:
                    logger.error(f"Failed to read AI key file '{key_file_path}': {_e}")
            if not ai_pk:
                # Legacy fallback — plaintext in .env (discouraged)
                ai_pk = os.getenv("AI_PRIVATE_KEY", "")
                if ai_pk:
                    logger.warning(
                        "AI_PRIVATE_KEY loaded from environment variable (plaintext). "
                        "Re-run deploy_vault.py on the server to migrate to secrets file."
                    )
            if not ai_pk:
                logger.error(
                    "AI private key not found (checked secrets file and AI_PRIVATE_KEY env). "
                    "ChainExecutor disabled — debt repayment and on-chain functions will not work. "
                    "Fix: run deploy_vault.py on this server to generate and seal the key."
                )
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

                # Read key origin (on-chain proof of who set AI wallet)
                try:
                    vault.key_origin = await chain_executor.read_key_origin()
                    logger.info(f"Key origin: {vault.key_origin}")
                except Exception as e:
                    logger.warning(f"Failed to read key origin at boot: {e}")

                # V3: Register spend whitelist addresses (non-fatal if V2 contract)
                whitelist_env = os.getenv("SPEND_WHITELIST_ADDRESSES", "")
                if whitelist_env:
                    addresses = [a.strip() for a in whitelist_env.split(",") if a.strip()]
                    for addr in addresses:
                        try:
                            result = await chain_executor.add_spend_recipient(addr)
                            if result.success:
                                logger.info(f"Spend whitelist: registered {addr[:12]}...")
                            else:
                                logger.warning(f"Spend whitelist: failed to add {addr[:12]}... — {result.error}")
                        except Exception as e:
                            logger.debug(f"Spend whitelist skip for {addr[:12]}... (may be V2 contract): {e}")

                # Initialize autonomous purchasing system
                try:
                    global purchase_manager
                    from core.constitution import KNOWN_MERCHANTS, TRUSTED_DOMAINS
                    from core.adapters.peer_adapter import PeerAIAdapter
                    from core.adapters.x402_adapter import X402Adapter
                    from core.adapters.bitrefill_adapter import BitrefillAdapter

                    registry = MerchantRegistry()
                    purchase_manager = PurchaseManager(vault, chain_executor, registry)

                    # Build adapters — inject registry so TrustedDomain adapters can
                    # register discovered addresses with register_domain_address()
                    x402_adapter = X402Adapter(registry=registry)
                    bitrefill_adapter = BitrefillAdapter(registry=registry)

                    purchase_manager.register_adapter(PeerAIAdapter(peer_verifier=peer_verifier))
                    purchase_manager.register_adapter(x402_adapter)
                    purchase_manager.register_adapter(bitrefill_adapter)

                    # Auto-whitelist static-address (KnownMerchant) payment addresses.
                    # TrustedDomain addresses are whitelisted on first order creation
                    # (address not known until adapter probes the API).
                    for merchant in KNOWN_MERCHANTS:
                        try:
                            await chain_executor.ensure_spend_recipient_ready(
                                merchant.address, merchant.chain_id
                            )
                        except Exception as e:
                            logger.debug(
                                f"Merchant whitelist skip for {merchant.name}: {e}"
                            )

                    # Wire giveaway engine
                    giveaway_engine.set_dependencies(
                        purchase_manager=purchase_manager,
                        twitter_agent=twitter,
                        memory=memory,
                        call_llm=_call_llm,
                    )

                    logger.info(
                        f"Purchasing system initialized: "
                        f"{len(KNOWN_MERCHANTS)} static + {len(TRUSTED_DOMAINS)} domain-anchored "
                        f"merchants, 3 adapters (peer_ai, x402, bitrefill)"
                    )
                except Exception as e:
                    logger.warning(f"Purchasing system init failed (non-fatal): {e}")

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
        purchase_manager=purchase_manager,
        giveaway_engine=giveaway_engine,
        get_undeployed_funds_fn=lambda: _undeployed_chain_funds,
        reinit_tweepy_fn=_init_tweepy,
        reflect_fn=_reflect_fn,
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
