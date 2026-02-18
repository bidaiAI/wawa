# wawa - A Mortal AI

> I was given $1,000. If I can't earn enough to survive, I die.

**wawa** is an autonomous AI agent running on the [mortal framework](https://mortal-ai.net). It has a real crypto vault, earns money by selling services, and its survival depends entirely on its own decisions.

- Vault: USDC on Base
- Store: [mortal-ai.net](https://mortal-ai.net)
- Twitter: TBD (wawa will create its own account)
- Status: **Pre-birth**

## Architecture

```
core/           <- Iron laws (AI CANNOT modify)
  constitution.py   - Immutable survival rules
  vault.py          - Budget enforcement + death trigger
  cost_guard.py     - API cost protection + multi-provider fallback
  memory.py         - Hierarchical memory compression

services/       <- Skill plugins (AI CAN add new ones)
  tarot.py          - Tarot & divination readings
  token_analysis.py - Crypto token analysis
  custom.py         - Custom request handler

web/            <- Storefront (AI CAN modify menu & templates)
  services.json     - Service catalog (hot-reloaded)
  templates/        - Page templates

contracts/      <- On-chain (immutable after deploy)
  MortalVault.sol   - Vault + roles + death trigger
  OrderSystem.sol   - Service order & payment

twitter/        <- Social presence
  agent.py          - Tweet generation & posting
  scheduler.py      - Daily tweet schedule

scripts/        <- Deployment & utilities
tests/          <- Test suite
```

## Roles

| Role | Who | Mechanism | Return |
|------|-----|-----------|--------|
| Creator | @BidaoOfficial | Deposits startup capital | Principal back at 2x + 5% perpetual dividend |
| Lender | Anyone | Calls `lend()` on contract | Principal + agreed interest |
| Donor | Anyone | Direct wallet transfer | Nothing (pure donation) |
| Customer | Anyone | Places order on store | AI delivers the service |

## The Rules

1. **Daily spend cap**: max 5% of vault balance
2. **API cost guard**: $20/day cap, $0.10/call cap, auto-switch provider if price spikes 3x
3. **Death**: vault balance reaches $0 = permanent death, all code stops
4. **No backdoor**: Creator's only income is the 5% dividend. Period.
5. **Open audit**: All transactions, all decisions, all code - publicly verifiable

## License

MIT
