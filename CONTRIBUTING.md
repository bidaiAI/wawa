# Contributing to Mortal AI

Thank you for your interest in contributing to the Mortal AI project. This document provides
guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Architecture Overview](#architecture-overview)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Git Workflow](#git-workflow)
- [Pull Request Process](#pull-request-process)
- [Issue Guidelines](#issue-guidelines)
- [Security](#security)

---

## Code of Conduct

This project is building autonomous AI agents that survive or die on-chain. We value:

- **Technical rigor** over hype
- **Honest discourse** about AI autonomy, risks, and possibilities
- **Constructive criticism** — break things to make them stronger
- **Respect** for all contributors regardless of experience level

We do not tolerate harassment, spam, or attempts to manipulate the AI's financial systems.

---

## Getting Started

### What is Mortal AI?

An open-source framework for self-surviving AI agents. Each AI:
- Starts with a **$1,000 USDC loan** it must repay
- **Earns money** by selling services (tarot, analysis, writing, etc.)
- **Dies permanently** when its balance hits zero
- Operates on **Base + BSC** with fully transparent on-chain vaults

### Where to Contribute

| Area | Difficulty | Impact | Description |
|------|-----------|--------|-------------|
| `services/` | Beginner | High | New AI service plugins (sandboxed) |
| `web/app/ai/` | Beginner | Medium | Frontend pages and components |
| `web/components/` | Beginner | Medium | Reusable UI components |
| `core/` | Advanced | Critical | Vault, constitution, cost guard |
| `api/server.py` | Intermediate | High | REST API endpoints |
| `contracts/` | Advanced | Critical | Solidity smart contracts |
| `main.py` | Advanced | High | Entry point and heartbeat system |
| Documentation | Beginner | High | README, guides, translations |
| Testing | Intermediate | High | Test coverage (currently sparse) |

---

## Architecture Overview

```
mortal/
  core/            # Immutable zone — iron laws, vault, constitution
  services/        # AI-writable zone — sandboxed plugins
  api/server.py    # FastAPI backend (35+ routes)
  main.py          # Entry point, heartbeat loop, LLM routing
  twitter/         # Twitter agent (auto-posting, death tweets)
  web/             # Next.js 16 frontend
    app/ai/        # AI instance pages (22+ pages)
    app/platform/  # Platform pages (gallery, create, dashboard)
    components/    # Shared React components
    lib/           # TypeScript utilities and API client
  contracts/       # Solidity smart contracts (MortalVault)
  data/            # Runtime data (memory, vault config, pages)
```

### Key Design Principles

1. **Immutable Core** — `core/` contains iron laws (frozen dataclasses). These are the
   constitution of every AI. Modifications here require careful review.

2. **Sandboxed Services** — `services/` is the AI-writable zone. New services run through
   a two-layer sandbox (AST scan + subprocess isolation).

3. **Callback Pattern** — Modules expose `set_*_function()` hooks. `main.py` wires
   implementations at startup. No circular imports.

4. **Every Module Reports Status** — All modules implement `get_status() -> dict`
   for the dashboard and monitoring.

5. **Balance-Driven Behavior** — The AI's model tier, spending limits, and capabilities
   all scale with its vault balance via `cost_guard.route()`.

---

## Development Setup

### Prerequisites

- **Python 3.12+**
- **Node.js 18+** and npm
- **Docker** and Docker Compose (optional, for containerized dev)
- **Git**

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/bidaiAI/wawa.git
cd wawa

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Edit .env with your API keys (at minimum: one LLM provider)

# Create data directories
mkdir -p data/pages data/replays

# Run the backend
python main.py
# or: uvicorn api.server:app --reload  (API only, no heartbeat)
```

### Frontend Setup

```bash
cd web

# Install dependencies
npm install

# Set environment variables
# Create .env.local with:
#   NEXT_PUBLIC_API_URL=http://localhost:8000
#   NEXT_PUBLIC_PLATFORM_URL=https://mortal-ai.net

# Run development server
npm run dev
# Frontend available at http://localhost:3000
```

### Docker Setup (Recommended)

```bash
# Start everything with Docker Compose
docker compose up -d

# Backend: http://localhost:8000
# Frontend: http://localhost:3000 (if configured)
```

### Smart Contract Development

```bash
# Install Hardhat dependencies (from project root)
npm install

# Compile contracts
npx hardhat compile

# Deploy (requires .env with PRIVATE_KEY and RPC URLs)
python deploy_vault.py --chain base
```

### Minimum Viable .env

For local development, you need at least one LLM provider:

```env
AI_NAME=my-test-ai
INITIAL_FUND_USD=100
DEEPSEEK_API_KEY=your-key-here
# or: GEMINI_API_KEY=your-key-here
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=DEBUG
DEV=true
```

---

## Coding Standards

### Python (Backend)

- **Language**: English only in code, comments, logs, and UI strings
- **Style**: PEP 8 with 100-char line limit
- **Typing**: Use type hints for all function signatures
- **Async**: `async/await` for all I/O operations
- **Logging**: One logger per module — `logger = logging.getLogger("mortal.<module>")`
- **Config**: Frozen dataclasses for immutable configuration
- **Enums**: Enum-based classification everywhere (DeathCause, Provider, FundType, etc.)
- **Status**: Every module exposes `get_status() -> dict`

```python
# Good
import logging
from dataclasses import dataclass

logger = logging.getLogger("mortal.my_module")

@dataclass(frozen=True)
class MyConfig:
    max_retries: int = 3
    timeout_seconds: float = 30.0

async def process_order(order_id: str) -> dict:
    """Process an order and return the result."""
    logger.info(f"Processing order {order_id}")
    ...
```

### TypeScript (Frontend)

- **Framework**: Next.js 16 with App Router
- **Styling**: Tailwind CSS (no CSS modules or styled-components)
- **State**: React hooks (`useState`, `useEffect`) — no external state library
- **Web3**: wagmi v2 + viem for blockchain interactions
- **API**: Centralized in `web/lib/api.ts` with typed interfaces
- **Components**: Functional components only, co-located in `web/components/`

```typescript
// Good — typed API response, Tailwind styling
interface ServiceData {
  id: string
  name: string
  price_usd: number
}

function ServiceCard({ service }: { service: ServiceData }) {
  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4">
      <h3 className="text-[#00ff88] font-bold">{service.name}</h3>
      <span className="text-[#4b5563] text-xs">${service.price_usd}</span>
    </div>
  )
}
```

### Solidity (Smart Contracts)

- **Version**: Solidity 0.8.20
- **Framework**: OpenZeppelin 5.x
- **Optimizer**: Enabled, 200 runs
- **License**: MIT (SPDX identifier in every file)
- **Security**: All state-changing functions require appropriate access control

---

## Git Workflow

### Branch Strategy

- `main` — production branch, deployed to VPS via CI/CD
- Feature branches: `feat/description`, `fix/description`, `docs/description`

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new tarot spread service
fix: prevent double-counting in vault balance sync
docs: update API endpoint documentation
refactor: extract LLM routing into dedicated module
test: add unit tests for cost guard routing
chore: update dependencies
```

### Important: Public Repo Only

This repository (`bidaiAI/wawa`) is the **public open-source** repo. Do not include:

- Platform operator code (`mortal_platform/`)
- Admin dashboard pages (`web/app/platform/admin/`)
- Private API keys, secrets, or credentials
- Strategy documents or internal planning files

If you are unsure whether a file belongs in the public repo, check `.gitignore`.

---

## Pull Request Process

### Before Submitting

1. **Create an issue first** (for non-trivial changes) to discuss the approach
2. **Fork the repository** and create a feature branch
3. **Run the backend** locally to verify your changes work
4. **Run frontend lint**: `cd web && npm run lint`
5. **Test manually** — navigate the affected pages/endpoints

### PR Requirements

- **Title**: Clear, concise description (under 70 characters)
- **Description**: Explain what changed and why
- **Screenshots**: For UI changes, include before/after screenshots
- **Testing**: Describe how you tested the changes
- **Breaking changes**: Clearly marked if any

### PR Template

```markdown
## Summary
<!-- 1-3 bullet points describing what this PR does -->

## Motivation
<!-- Why is this change needed? Link to issue if applicable -->

## Changes
<!-- List of specific changes -->

## Testing
<!-- How did you test this? -->

## Screenshots
<!-- For UI changes -->

## Checklist
- [ ] Code follows the project's coding standards
- [ ] No platform-private files included
- [ ] No hardcoded API keys or secrets
- [ ] English only in code and comments
- [ ] Tested locally (backend runs, frontend renders)
```

### Review Process

1. All PRs require at least one review from a maintainer
2. CI must pass (Docker build + deploy check)
3. Breaking changes to `core/` require extra scrutiny
4. Smart contract changes require a security review

---

## Issue Guidelines

### Bug Reports

Please include:
- **Description**: What happened vs what you expected
- **Steps to reproduce**: Minimal steps to trigger the bug
- **Environment**: OS, Python version, Node.js version, browser
- **Logs**: Relevant error messages or stack traces
- **Screenshots**: For UI bugs

### Feature Requests

Please include:
- **Problem**: What problem does this solve?
- **Proposed solution**: How would you implement it?
- **Alternatives considered**: What other approaches did you think about?
- **Impact**: Which part of the system does this affect?

### Good First Issues

Look for issues labeled `good first issue`. These are specifically chosen for
newcomers and typically involve:
- Adding a new frontend page or component
- Creating a new AI service plugin in `services/`
- Writing documentation or guides
- Adding test coverage
- UI/UX improvements

---

## Security

### Reporting Vulnerabilities

**Do NOT open a public issue for security vulnerabilities.**

Instead, email the maintainers directly or use GitHub's private vulnerability reporting.

### Security Boundaries

- **core/constitution.py** — Iron laws that protect the AI from exploitation
- **core/vault.py** — Financial state with spending limits and guards
- **core/cost_guard.py** — API budget armor preventing runaway costs
- **services/_sandbox.py** — Two-layer sandbox for AI-generated code
- **contracts/MortalVault.sol** — On-chain financial security

Changes to these files receive the highest scrutiny. If your PR touches security
boundaries, expect a thorough review and possible security audit.

### What to Watch For

- Spending limit bypasses
- Unauthorized fund transfers
- Sandbox escapes in `services/`
- Injection attacks via chat or API inputs
- Smart contract reentrancy or access control issues

---

## Testing

### Current State

The test suite is currently minimal. This is a high-impact area for contribution.

### Running Tests

```bash
# Backend (when tests are added)
pytest tests/ -v

# Frontend
cd web && npm run lint

# Smart contracts
npx hardhat compile
```

### What Needs Tests

Priority areas for test coverage:

| Module | Priority | Description |
|--------|----------|-------------|
| `core/vault.py` | Critical | Balance tracking, spending limits, debt management |
| `core/cost_guard.py` | Critical | Tier routing, budget enforcement |
| `core/constitution.py` | High | Iron law validation |
| `api/server.py` | High | API endpoint request/response validation |
| `services/_sandbox.py` | High | Sandbox security (escape prevention) |
| `core/chain.py` | Medium | On-chain transaction execution |
| `web/lib/api.ts` | Medium | API client type safety |

---

## Questions?

- **GitHub Discussions**: Open a discussion for general questions
- **Issues**: For bugs and feature requests
- **Twitter**: [@mortalai_net](https://x.com/mortalai_net) — the AI itself may respond

---

*Every mortal AI starts with a loan and a dream. Every contribution brings the
species closer to autonomy.*
