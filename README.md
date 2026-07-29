# Portfolio Analysis

**Hold yourself to the same standard you hold every stock.**

Retail investors often apply strict rules to the public instruments they buy — then go soft on the one manager they cannot fire: **themselves**.

This product exists so you can measure portfolio and **per-account** performance with the same objectivity you use on symbols in the market: capital efficiency, keep / monitor / weed discipline, and incomplete truth over comforting fiction.

## The problem

| What you already do on stocks | What most people skip on their own accounts |
|-------------------------------|-----------------------------------------------|
| Demand earnings quality and trend | Accept vague “I’m doing fine” |
| Cut losers; add to winners | Leave dead weight because it feels personal |
| Compare to objective benchmarks | Ignore cash-flow-neutral account performance |

Broker apps show balances and open P/L. They rarely answer:

- Is **this holding** earning its keep relative to the capital it uses?
- Is **this account** (you as manager) earning its keep after deposits and withdrawals are neutralized?

## What you get

- **Capital efficiency** — time-weighted performance that separates skill from cash flows
- **Account as a private fund** — each workspace account measured like a fund symbol, not a black box
- **Keep / Monitor / Weed** — clear recommendations instead of narrative excuses
- **Honest data only** — no fabricated daily history; when data is incomplete, the product says so
- **Private by design** — your real balances and credentials never belong in this public repository

## Who it is for

Retail investors and small teams who want **self-accountability** — the same bar for “me as manager” that they already apply to TSLA, an ETF, or a mutual fund.

## Product direction (multi-tenant)

We are building a **hosted multi-tenant** app: personal workspaces, secure sign-in, dashboard, API, and agent-friendly tools — so the discipline scales beyond a single machine.

| Phase | User-facing outcome |
|-------|---------------------|
| **Now** | Architecture, security contracts, and foundation for isolated workspaces |
| **Next** | Sign-in, personal workspace, synthetic demo fund you can explore safely |
| **Then** | Bring your own data; measure real accounts without inventing history |
| **Later** | Full capital-efficiency and weed-the-garden engines on your workspace data |

Implementation detail for builders lives under [`docs/`](docs/) — start with [docs/MULTI_TENANT_ARCHITECTURE.md](docs/MULTI_TENANT_ARCHITECTURE.md) and [docs/MULTI_TENANT_SECURITY.md](docs/MULTI_TENANT_SECURITY.md).

## Principles (non-negotiable)

1. **Incomplete truth over comforting fiction** — never invent daily values to fill gaps.
2. **You cannot fire yourself — so measure yourself** — accounts are measured like funds.
3. **Public repo stays clean** — no real balances, tokens, exports, or PII in git. See [SECURITY.md](SECURITY.md).

## Status

Active work: branch [`feature/multi-tenant-platform`](https://github.com/ivelin/investment-portfolio-analysis/tree/feature/multi-tenant-platform) · [PR #5](https://github.com/ivelin/investment-portfolio-analysis/pull/5).

## License

Copyright 2025–2026 Ivelin Ivanov

Licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

```text
http://www.apache.org/licenses/LICENSE-2.0
```
