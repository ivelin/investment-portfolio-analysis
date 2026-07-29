# Multi-tenant platform architecture

**Goal:** Hosted multi-tenant portfolio analysis with web UI, REST, and MCP —
strict tenant isolation, per-tenant broker OAuth (correct model per broker),
and agent parity with the dashboard.

See also: [BROKER_OAUTH.md](./BROKER_OAUTH.md), [MULTI_TENANT_SECURITY.md](./MULTI_TENANT_SECURITY.md).

## Non-negotiable isolation rules

1. **No shared broker feed.** Never load one user’s Schwab/Robinhood/IBKR data
   into another tenant (including operator/Grok MCP sessions).
2. **Every portfolio row carries `tenant_id`.** Membership or API-key → tenant first.
3. **OAuth is per tenant.** User tokens only in `connector_secrets` for that `tenant_id`.
4. **Surfaces share one service.** Web, REST, and MCP call the same PortfolioService.
5. **Public repo hygiene.** No balances, tokens, exports, or raw account numbers in git.

## Broker auth models (different on purpose)

| Broker | Model | Notes |
|--------|--------|------|
| Schwab | Direct Trader API OAuth + PKCE | Matches upstream `schwab/auth.py`; needs `SCHWAB_CLIENT_ID`/`SECRET` |
| Robinhood | Hosted MCP OAuth 2.1 + DCR | `https://agent.robinhood.com/mcp/trading` |
| IBKR | Hosted MCP OAuth 2.1 + DCR | `https://api.ibkr.com/v1/api/mcp-public` |

App-level DCR client ids live in `platform_oauth_clients` (not user data).
User tokens never live there.

## Gradio

Not the multi-tenant shell. TanStack Start + shared service + MCP/REST.
Optional later: Gradio notebook over tenant API key only.

## Control map (SOX-oriented)

| Control | Implementation |
|---------|----------------|
| Access | Session + tenant API keys + roles |
| Segregation | `tenant_id` on all portfolio tables |
| Audit | `audit_events` redacted |
| Secrets | AES-GCM envelope when `CONNECTOR_SECRET_KEY` set |
| Completeness | Demo labeled; live only via that tenant’s tokens |

## MCP ↔ Web parity

| Web | MCP tool |
|-----|----------|
| Dashboard | `workspace_summary` |
| Accounts | `list_accounts` |
| Positions | `positions` |
| Series | `fund_series` |
| Brokers | `list_connectors` |

## Phased delivery

| Phase | Outcome |
|-------|---------|
| **0** | Tear down shared snapshot |
| **1** | Service layer + MCP parity + API keys |
| **2 (this)** | Correct per-broker OAuth + sync adapters |
| **3** | Export upload; scheduled sync; refresh hardening |
| **4** | Analysis engines |
| **5** | Collaborators, billing, audit UI |
