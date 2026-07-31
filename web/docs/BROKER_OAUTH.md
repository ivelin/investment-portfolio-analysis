# Per-tenant broker OAuth (API / MCP only)

Financial data. **Every user OAuth token is tenant-scoped.**

## Read-only hard rule

**Connectors never place orders or move money.** See [BROKER_READ_ONLY.md](./BROKER_READ_ONLY.md).

All outbound broker HTTP goes through `brokerFetch` + `read-only-policy.ts`.

## Brokers

| Broker | Path | Notes |
|--------|------|--------|
| **Schwab** | Trader API OAuth (PKCE + confidential client) | Read accounts/positions only |
| **Robinhood** | Agentic MCP OAuth (DCR + PKCE) | OAuth only; no trade tool calls |
| **IBKR** | MCP when discovery works | Same OAuth shell; read-only policy |
| **Fidelity** | Not wired | Setup needed |

## Code

| Piece | Path |
|-------|------|
| Read-only policy | `src/lib/portfolio/brokers/read-only-policy.ts` |
| Broker HTTP gate | `src/lib/portfolio/brokers/broker-http.ts` |
| Schwab OAuth + reads | `src/lib/portfolio/oauth/schwab.server.ts` |
| MCP OAuth (Robinhood) | `src/lib/portfolio/oauth/mcp-oauth.server.ts` |
| Callback | `src/routes/api/v1/oauth/$broker/callback.ts` |

## Schwab env (optional)

```text
SCHWAB_CLIENT_ID=
SCHWAB_CLIENT_SECRET=
SCHWAB_REDIRECT_URI=
CONNECTOR_SECRETS_KEY=
```
