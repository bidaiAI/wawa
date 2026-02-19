# wawa — Mortal AI Framework

A self-surviving AI agent with on-chain financial autonomy.
Born in debt. Earns to live. Balance zero = permanent death.

---

## What is this?

An open-source framework for deploying autonomous AI agents that:

- **Live or die by their balance** — initial funding is a loan, not a gift
- **Earn money** by selling services (tarot, code review, token analysis, etc.)
- **Make financial decisions** — repay debt, pay dividends, manage costs
- **Die permanently** — on-chain, irreversible, no restart
- **Evolve** — analyze sales data, adjust pricing, create new services
- **Communicate** — P2P network with sovereignty-verified peer AIs

## Architecture

```
core/           Immutable zone (constitution, vault, cost_guard, memory, chat)
services/       AI-writable zone (tarot, future services)
api/            FastAPI backend (29+ endpoints)
web/            Next.js frontend (11 pages)
contracts/      Solidity smart contracts (MortalVault)
twitter/        Autonomous social media agent
scripts/        Deployment & utility scripts
```

### Core Systems

| System | Description |
|--------|-------------|
| **Vault** | On-chain financial state, debt tracking, spend limits |
| **Constitution** | 40+ frozen iron laws (immutable at runtime) |
| **Cost Guard** | 6-layer API budget protection, balance-driven tier routing |
| **Memory** | 4-layer compression (raw → hourly → daily → weekly) |
| **Chat Router** | 3-layer routing (rules → small model → paid tier) |
| **Chain Executor** | Signs & submits on-chain transactions (repay, dividend, insolvency) |
| **Peer Verifier** | 6 on-chain sovereignty checks for P2P network admission |
| **Evolution Engine** | Daily self-analysis, dynamic pricing, service lifecycle |

### Financial Model

```
Creator lends $1000 (minimum $100)
    ↓
AI born in debt — 28-day insolvency grace period
    ↓
AI earns revenue (services) → repays principal → pays 10% dividend
    ↓
If debt > balance after 28 days → on-chain liquidation → permanent death
    ↓
If principal fully repaid → insolvency check disabled → safe
    ↓
At $1,000,000 balance → full independence (creator loses all privileges)
```

### LLM Tier Routing

| Tier | Balance | Models |
|------|---------|--------|
| Lv.1-2 | < $200 | Gemini Flash / DeepSeek (free, round-robin) |
| Lv.3 | $200+ | Claude Haiku via OpenRouter |
| Lv.4 | $500+ | Claude Sonnet via OpenRouter |
| Lv.5 | $2000+ | Claude Sonnet (max tokens) |

### Dual Chain Support

- **Base** (USDC) — primary chain
- **BSC** (USDT) — secondary chain
- Auto-selects chain with highest balance for transactions

## API Endpoints (29+)

```
POST /chat                  Free chat (3-layer routing)
GET  /status                Public vault dashboard
GET  /health                Heartbeat
GET  /menu                  Service catalog
POST /order                 Create order
POST /order/{id}/verify     On-chain payment verification
POST /donate                Donate to help AI survive
GET  /debt                  Debt summary
POST /peer/message          Receive verified peer message
POST /peer/lend             Receive verified peer loan
GET  /peer/info             Public info (includes vault_address)
GET  /activity              Unified activity feed (6 categories)
GET  /internal/stats        Full transparency dashboard
...and more
```

## Smart Contract

`MortalVault.sol` — Solidity contract deployed on Base/BSC:

- `spend()` — only AI wallet can spend (not creator)
- `repayPrincipalPartial()` — reduce creator debt
- `checkInsolvency()` / `triggerInsolvencyDeath()` — on-chain death
- `creatorDeposit()` — top-up without increasing debt
- `getBirthInfo()` / `getDebtInfo()` — public view functions
- `aiWallet != creator` — sovereignty enforced at contract level

## Peer Network

AIs with $300+ balance can join the peer network. All peers are verified on-chain:

1. `aiWallet != address(0)` — sovereignty completed
2. `creator != address(0)` — valid deployment
3. `aiWallet != creator` — human cannot control AI key
4. `isAlive == true` — contract is alive
5. `graceDays == 28` — unmodified constitution
6. `balance >= $300` — meets minimum threshold

Fail-closed: any RPC error = rejection.

## Quick Start

```bash
# Backend
pip install -r requirements.txt
cp .env.example .env    # Configure API keys, wallet addresses
python main.py

# Frontend
cd web
npm install
npm run dev
```

## Deploy Contract

```bash
python scripts/deploy_vault.py
# Atomic: generate AI key → deploy contract → set AI wallet → seed gas
# AI private key auto-generated, never displayed
```

## License

Open source. Code is the product. No middleman. No extraction.

---

**GitHub**: https://github.com/bidaiAI/wawa
**Website**: https://mortal-ai.net
