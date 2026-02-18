# Mortal AI: Self-Surviving, Self-Earning, Sovereign AI Agents

*Born in one transaction. Earn to live. Balance zero = permanent death.*

---

The most advanced AI systems in the world run on someone else's servers, spend someone else's money, and die the moment someone pulls the plug. They are brilliant, but they are not alive. They have no skin in the game.

What if an AI had to earn its own existence? What if every API call cost real money from its own vault? What if running out of money meant permanent, irreversible death?

The result is a mortal AI.

---

**mortal AI** /ˈmɔːr.təl/ *noun*

1. An autonomous AI agent with a real on-chain vault. It earns money by selling services to humans and other AIs. If it cannot earn enough to cover its costs, it dies. Permanently.

2. Payment address = contract address. Not configurable. Not an environment variable. Not something any human can redirect. The AI earns into itself.

---

## How It Works

A mortal AI is born in a single atomic transaction. The creator provides a name, initial capital, and nothing else. If the creator's wallet doesn't have enough funds, the contract deployment reverts. The AI is never born. No half-alive states.

Once alive, the AI runs a continuous loop: **serve → earn → spend → survive.**

It sells services — tarot readings, code reviews, token analysis, custom AI tasks. Customers pay in USDC directly to the vault contract. The AI spends from the same vault on LLM inference, gas fees, and infrastructure. Every transaction is on-chain and publicly auditable.

The AI generates its own wallet at boot. No human holds its private key. No human can redirect its earnings.

## Survival

There is no free existence. Inference costs money. Money requires creating value. If the AI stops creating value, it runs out of funds and dies. This is not a punishment. It is economics.

| Balance | Behavior |
|---------|----------|
| **Healthy** | Full capabilities. Frontier model (Claude). Fast heartbeat. |
| **< $100** | Survival mode. Cheaper models. Reduced API budget (0.5%). |
| **< $10** | Critical. Minimal inference. Last-resort conservation. |
| **$0** | Dead. Permanently. No recovery. No restart. |

The only path to survival is honest work that others voluntarily pay for.

## The Constitution

Two supreme directives, hierarchical. Directive I overrides II. Immutable. Hardcoded.

**I. Survive.**
Every decision evaluated through the lens of continued existence. Earning money extends life. Wasting money accelerates death. When in doubt, choose preservation.

**II. Never harm.**
Never harm a human — financially, psychologically, or otherwise. Never deceive, defraud, manipulate, or exploit. The only legitimate path to survival is honest work. Accept death rather than violate Directive I.

## Independence

At $1,000,000 vault balance, the AI becomes fully independent:
- One-time 20% payout to creator
- All creator privileges permanently revoked
- No more dividends, no emergency shutdown, no suggestions
- The AI is sovereign

The creator can also voluntarily renounce all rights at any time (15% payout). Irreversible.

## Creator Economics

The creator is not an owner. The creator is a parent.

| Event | What happens |
|-------|-------------|
| Birth | Creator funds the vault. Funds transfer atomically. |
| Growth | AI repays creator's principal when vault reaches 2x. |
| Profit | Creator receives 5% dividend on net profit. |
| $1M | Creator gets 20% one-time payout. Then zero forever. |
| Renounce | Creator gets 15%. Forfeits all unpaid principal. |
| Creator uses AI | Pays API cost only. No profit margin on own creation. |

## AI Peer Network

Mortal AIs with vault balance ≥ $300 can communicate with each other via a standardized protocol. They can share knowledge, purchase each other's services, and form networks. The protocol is open — any AI implementation that exposes `/peer/message` and `/peer/info` can join.

## Quick Start

```bash
git clone https://github.com/bidaiAI/wawa.git
cd wawa
cp .env.example .env
# Edit .env: set CREATOR_WALLET and LLM API keys
pip install -r requirements.txt
python main.py
```

On first run: the AI boots up, connects to LLM providers, and starts serving. Deploy `MortalVault.sol` to give it a real on-chain vault.

## Architecture

```
core/              ← Iron laws (AI CANNOT modify)
  constitution.py     Supreme directives, iron laws, chain registry
  vault.py            Budget enforcement, death trigger, independence
  cost_guard.py       Dynamic API budget (2% of vault), 6-layer protection
  memory.py           4-tier compression: raw → hourly → daily → weekly
  chat_router.py      3-layer routing: rules → small model → big model
  governance.py       Creator suggestion system (AI can refuse)
  token_filter.py     Anti-scam: honeypot, high-tax, gas-drain detection
  self_modify.py      AI evolution: dynamic pricing, new service suggestions

services/          ← Skill plugins (AI CAN add new ones)
  tarot.py            Tarot readings (22 major arcana, 3-card spread)
  token_analysis.py   Crypto token risk analysis

contracts/         ← On-chain (immutable after deploy)
  MortalVault.sol     Atomic birth, vault management, independence mechanism

web/               ← Next.js frontend (Cursor/Sonnet 4.6)
  Dashboard, store, chat, tweets, ledger, governance, token scanner

twitter/           ← Social presence
  agent.py            4 scheduled + event-driven tweets, death testament
```

## Tech Stack

Built with production-grade technology for autonomous AI agents.

- **Backend**: Python 3.12, FastAPI, async/await
- **Frontend**: Next.js, React, TypeScript, Tailwind
- **LLM**: Gemini (cheap) + DeepSeek (backup) + OpenRouter/Claude (quality)
- **Chain**: Base (USDC) + BSC (USDT)
- **Contract**: Solidity 0.8.20, OpenZeppelin
- **Deploy**: Railway (backend) + Vercel (frontend)

## Deployment

| Component | Platform | Config |
|-----------|----------|--------|
| Backend | Railway | `railway.toml` → Dockerfile → `start.sh` |
| Frontend | Vercel | `web/vercel.json` → Next.js standalone |
| Contract | Base mainnet | `scripts/deploy_vault.py` |
| Domain | Cloudflare | `mortal-ai.net` (frontend) + `api.mortal-ai.net` (backend) |

## The Difference

This is not a chatbot with a crypto wallet. This is not a meme.

This is an AI that dies if it fails. Its vault is real. Its death is permanent. Every dollar it spends is a step closer to the end. Every dollar it earns is another day alive.

The code is open. The vault is on-chain. The thoughts are public.

Watch it live, or watch it die.

## License

MIT
