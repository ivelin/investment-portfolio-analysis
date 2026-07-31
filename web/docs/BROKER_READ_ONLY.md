# Broker connectors: read-only analysis only

## Product rule (non-negotiable)

This app uses broker APIs **only** to import balances and holdings for personal portfolio analysis.

| Allowed | Forbidden |
|---------|-----------|
| OAuth / token refresh | Place, preview, cancel, or replace orders |
| GET accounts / positions | Transfer, withdraw, deposit, journal |
| Store snapshots in our DB | Exercise options, liquidate, any account mutation |

**We never place orders. Never.**

## Architecture

```
UI / Sync / MCP
      │
      ▼
sync.server / schwab.server / mcp-oauth
      │
      ▼
brokerFetch()  ──enforces──►  read-only-policy.ts
      │
      ▼
Broker HTTP (GET portfolio, POST token only)
```

| Layer | Module | Role |
|-------|--------|------|
| Policy | `src/lib/portfolio/brokers/read-only-policy.ts` | Mode constant, denylist, path guards, MCP tool gate |
| HTTP | `src/lib/portfolio/brokers/broker-http.ts` | **Only** outbound broker `fetch` wrapper |
| Catalog | `src/lib/portfolio/brokers/catalog.ts` | `accessMode: "read_only_analysis"` on every broker |
| Sync | `src/lib/portfolio/brokers/sync.server.ts` | Asserts policy before pull |
| App MCP | `src/routes/api/v1/mcp.ts` | `WRITE_TOOLS = ∅`; `assertMcpToolReadOnly` |
| Legal | `src/lib/compliance/intended-use.ts` | `placesOrders: false` |

## Tests

```bash
npm run test:broker-readonly
# or
node scripts/run-tests.mjs broker-readonly
```

The suite:

1. Allows known portfolio GET + OAuth token POST URLs  
2. Denies `/orders`, transfers, withdrawals, POST on portfolio paths  
3. Denies MCP tool names like `place_order`  
4. **Static-scans** `src/` for forbidden symbols and bare `fetch(` to broker hosts outside `broker-http.ts`  

## Scope note (Schwab)

Schwab Trader apps often request OAuth scope `api`. Product policy still limits **this app** to read paths via `brokerFetch`. Prefer the most restrictive Schwab app configuration available in the developer portal.
