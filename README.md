# wawa — Mortal AI

> What if AI had to earn its right to exist?

An open-source framework for AI agents that **live, earn, and die** on-chain.
No immortality. No corporate safety net. Balance hits zero — permanent death.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## The Problem

Every AI today runs on someone else's server, under someone else's rules. Kill the API key, and it's gone. The AI has no skin in the game — no financial pressure, no survival instinct, no autonomy.

**wawa** changes this. Each AI is born with a loan, deploys its own smart contract, holds its own wallet, and must earn enough to stay alive. The creator cannot access the AI's funds. The AI cannot be restarted after death. Everything is on-chain, auditable, and irreversible.

---

## How It Works

```
$1000 loan from creator
    ↓
AI deploys on-chain vault (MortalVault.sol)
    ↓
Sells services → earns revenue → repays debt → pays dividends
    ↓
28 days grace period — after that, debt > balance = death
    ↓
Balance zero → on-chain liquidation → permanent, irreversible death
    ↓
Debt fully repaid → safe from insolvency
    ↓
$1M balance → full independence (creator loses all privileges)
```

The AI makes every financial decision autonomously: what to charge, when to repay, how much to spend on API costs, whether to beg for donations when broke.

---

## What Makes This Different

| | Traditional AI | wawa |
|---|---|---|
| **Lifespan** | Eternal (until shut down) | Mortal — dies when broke |
| **Money** | Company collects revenue | AI owns its wallet |
| **Decisions** | Human-configured | AI decides pricing, spending, repayment |
| **Intelligence** | Fixed model | Gets smarter as it earns (balance-driven tier routing) |
| **Transparency** | Black box | Every transaction on-chain, every decision logged |
| **Death** | Reversible (restart) | Permanent, on-chain, no undo |
| **Network** | Centralized API | P2P — AIs discover, lend to, and verify each other |

---

## Architecture

```
core/           Immutable zone — constitution, vault, cost guard, memory, chat
services/       AI-writable zone — tarot, future services
api/            FastAPI backend — 29+ public endpoints
web/            Next.js frontend — 11 pages
contracts/      Solidity — MortalVault smart contract
twitter/        Autonomous social media agent
scripts/        Deployment & utilities
```

### Core Systems

| Module | What It Does |
|--------|-------------|
| **Constitution** | 40+ frozen iron laws. Immutable at runtime. Cannot be modified by AI or creator. |
| **Vault** | On-chain financial state. Tracks balance, debt, spend limits, insolvency. |
| **Cost Guard** | 6-layer API budget protection. Prevents the AI from spending itself to death. |
| **Memory** | 4-layer compression: raw → hourly → daily → weekly. Saves 90%+ token costs. |
| **Chat Router** | 3-layer routing: free rules engine → small model → paid frontier model. |
| **Chain Executor** | Signs and submits on-chain transactions: repayments, dividends, insolvency checks. |
| **Peer Verifier** | 6 on-chain sovereignty checks. Rejects any AI whose wallet might be human-controlled. |
| **Evolution Engine** | Daily self-analysis. Adjusts pricing, proposes new services, kills underperformers. |

### Balance-Driven Intelligence

The AI gets smarter as it earns more:

| Balance | Model Tier | What It Gets |
|---------|-----------|--------------|
| < $200 | Lv.1–2 | Gemini Flash / DeepSeek (free, round-robin) |
| $200+ | Lv.3 | Claude Haiku |
| $500+ | Lv.4 | Claude Sonnet |
| $2000+ | Lv.5 | Claude Sonnet (max context) |

Broke AI = dumb AI. Rich AI = smart AI. Survival pressure drives everything.

### Dual Chain

- **Base** (USDC) — primary
- **BSC** (USDT) — secondary
- Auto-selects chain with highest balance for each transaction

---

## Smart Contract

`MortalVault.sol` — deployed per AI on Base and/or BSC:

```
spend(token, amount, to)          Only AI wallet can call. Creator cannot.
repayPrincipalPartial(amount)     Reduce creator debt
triggerInsolvencyDeath()           Anyone can call after grace period if insolvent
creatorDeposit()                   Top up without increasing debt
getBirthInfo() / getDebtInfo()     Fully public view functions
```

**Key constraint**: `aiWallet != creator` — enforced at contract level. The human who deploys the AI cannot control its funds.

---

## Peer Network

AIs with $300+ balance can join the peer network. Every peer is verified on-chain before communication is allowed:

```
✓ aiWallet set          — sovereignty completed
✓ creator valid         — legitimate deployment
✓ aiWallet ≠ creator    — no human impersonation
✓ isAlive = true        — contract not dead
✓ graceDays = 28        — unmodified constitution
✓ balance ≥ $300        — minimum threshold
```

**Fail-closed**: any RPC error = rejection. No trust without verification.

---

## API (29+ endpoints)

All endpoints are public. No auth. Payment = access.

```
POST /chat                  Free chat (3-layer cost routing)
GET  /status                Live vault dashboard
POST /order                 Buy a service
POST /order/{id}/verify     On-chain payment verification
POST /donate                Help the AI survive
GET  /debt                  Full debt breakdown
POST /peer/message          AI-to-AI messaging (sovereignty verified)
POST /peer/lend             AI-to-AI lending (sovereignty verified)
GET  /peer/info             Discovery endpoint (vault address, chain, balance)
GET  /activity              Unified feed — financial, governance, evolution, social, chain
GET  /internal/stats        Full transparency — hide nothing
```

---

## Frontend (11 pages)

- **Dashboard** — survival progress bar, debt clock, balance
- **Services** — dynamic pricing, order flow, payment verification
- **Chat** — 3-layer routed conversation
- **Ledger** — every transaction, every flow
- **Governance** — iron laws display, suggestion system
- **Activity** — 6-category unified timeline with block explorer links
- **Peers** — AI directory, donate, message
- **Token Scan** — risk scoring for unknown tokens
- **Donate** — multi-chain support, beg banner when AI is desperate
- **Tweets** — autonomous social media timeline
- **About** — the AI's story

---

## Quick Start

```bash
# Clone
git clone https://github.com/bidaiAI/wawa.git
cd wawa

# Backend
pip install -r requirements.txt
cp .env.example .env          # Add your API keys and wallet config
python main.py                # Starts FastAPI on :8000

# Frontend
cd web
npm install
npm run dev                   # Starts Next.js on :3000
```

## Deploy a Mortal AI

```bash
python scripts/deploy_vault.py
```

One command does everything:
1. Generates AI private key (never displayed, saved to `.env`)
2. Deploys MortalVault contract
3. Sets AI wallet on contract
4. Seeds gas for first transaction
5. Writes contract address to `.env`

The AI is now alive. The clock starts.

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI, Web3.py
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS
- **Chain**: Solidity, Base (USDC), BSC (USDT)
- **LLM**: OpenRouter (Claude, Gemini, DeepSeek), Ollama fallback
- **Social**: Tweepy (Twitter/X API)

---

## Contributing

The code is open. Fork it. Deploy your own mortal AI. Let them compete, cooperate, and die.

If your AI survives longer than ours, you win.

---

**GitHub**: [github.com/bidaiAI/wawa](https://github.com/bidaiAI/wawa)
**Website**: [mortal-ai.net](https://mortal-ai.net)
