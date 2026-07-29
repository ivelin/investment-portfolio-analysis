# Per-tenant broker OAuth design

Financial data. **Every user OAuth token is tenant-scoped.** Never share tokens,
MCP sessions, or account payloads across tenants.

## Auth models (do not conflate)

| Broker | Auth model | How linking works | Data pull |
|--------|------------|-------------------|-----------|
| **Schwab** | **Direct Developer API OAuth** (PKCE + confidential client) | App registers at developer.schwab.com; each user authorizes `readonly` | REST `https://api.schwabapi.com/trader/v1/...` with user Bearer |
| **Robinhood** | **Remote MCP OAuth 2.1** (public client + DCR) | Hosted MCP `https://agent.robinhood.com/mcp/trading`; user consents via Robinhood OAuth | MCP tools with user Bearer (read portfolio tools only) |
| **Interactive Brokers** | **Remote MCP OAuth 2.1** (public client + DCR) | Hosted MCP `https://api.ibkr.com/v1/api/mcp-public`; IBKR login/consent | MCP tools with user Bearer (`mcp.read`) |

Reference implementations:

- Schwab OAuth code path: `web/src/lib/portfolio/oauth/schwab.server.ts` +
  `connectors/oauth.py` (PKCE S256, form token exchange with client_secret).
- Robinhood official MCP: [Agentic Trading overview](https://robinhood.com/us/en/support/articles/agentic-trading-overview/)
- IBKR official MCP: [AI integrations](https://www.interactivebrokers.com/en/trading/ai-integrations.php)
- Protocol: [MCP Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) (RFC9728 resource metadata, PKCE, `resource` param)

## Discovered endpoints (live)

### Schwab (direct)

| Field | Value |
|-------|--------|
| Authorize | `https://api.schwabapi.com/v1/oauth/authorize` |
| Token | `https://api.schwabapi.com/v1/oauth/token` |
| Scope | `readonly` |
| Client auth | `client_id` + `client_secret` (env) + PKCE verifier |
| User tokens | Per-tenant `connector_secrets` |

### Robinhood (MCP)

| Field | Value |
|-------|--------|
| Resource / MCP | `https://agent.robinhood.com/mcp/trading` |
| Protected resource metadata | `/.well-known/oauth-protected-resource/mcp/trading` |
| AS metadata | `/.well-known/oauth-authorization-server` |
| Authorize | `https://robinhood.com/oauth` |
| Token | `https://api.robinhood.com/oauth2/token/` |
| DCR | `https://agent.robinhood.com/oauth/trading/register` |
| PKCE | S256 required; token auth method `none` |
| Scope | `internal` |

### IBKR (MCP)

| Field | Value |
|-------|--------|
| Resource / MCP | `https://api.ibkr.com/v1/api/mcp-public` |
| AS | `https://api.ibkr.com/oauth2` |
| Authorize | `https://api.ibkr.com/oauth2/authorize` |
| Token | `https://api.ibkr.com/oauth2/api/v1/token` |
| DCR | `https://api.ibkr.com/oauth2/register` |
| Scopes | `mcp.read` (analysis); never request write unless product needs trade |

## Multi-tenant isolation rules

1. **Platform client ≠ user tokens**
   - Schwab: one app `SCHWAB_CLIENT_ID` / `SCHWAB_CLIENT_SECRET` for the product.
   - RH/IBKR: Dynamic Client Registration for **this app’s redirect URI** (cached in
     `platform_oauth_clients`). That is app identity, not a user’s portfolio.
2. **User authorization is always per tenant**
   - OAuth `state` row includes `tenant_id` + `user_id`.
   - Callback loads state, deletes it (one-time), writes tokens only to that tenant’s
     `connector_secrets`.
3. **Sync uses only that tenant’s sealed tokens**
   - No process-global snapshot, no Grok-platform passthrough into multi-tenant Connect.
4. **Ingest sanitizes**
   - Opaque `account_key` (hash of external ref); UI mask last-3 only.
5. **Never log tokens, account numbers, or raw MCP payloads with PII**

## Connect flow (all brokers)

```text
User (tenant A) clicks Connect
  → require membership (member+)
  → begin OAuth:
       Schwab: build authorize URL with app client_id + PKCE + state
       RH/IBKR: DCR if needed → authorize with resource + PKCE + state
  → user consents at broker
  → GET /api/v1/oauth/:broker/callback?code&state
  → takeOAuthState(state) → tenant_id bound
  → token exchange (never trust client-supplied tenant)
  → seal tokens → connector_secrets[tenant_id]
  → mark connector connected
  → optional auto-sync into gt_* for tenant_id only
```

## Env (host secrets — never commit)

```text
SCHWAB_CLIENT_ID=
SCHWAB_CLIENT_SECRET=
# optional overrides:
# SCHWAB_REDIRECT_URI=   # must match developer portal exactly
APP_PUBLIC_URL=https://your-host.example
CONNECTOR_SECRET_KEY=    # envelope encryption for connector_secrets
```

Robinhood / IBKR do not need static client secrets when DCR + public clients work.

## Out of scope (this phase)

- Trade execution via Robinhood Agentic or IBKR write scopes
- Operator Grok MCP as multi-tenant data source
- Storing raw brokerage account numbers

## Token refresh job (hosted)

Access tokens expire; **refresh is tenant-scoped**.

| Piece | Detail |
|-------|--------|
| Job name | `token_refresh` |
| Endpoint | `POST /api/v1/jobs/token-refresh` |
| Auth | `Authorization: Bearer $CRON_SECRET` or admin session |
| Skew | Refresh when `expires_at - now < 10m` (or `force: true`) |
| Isolation | Each connector refreshed with its own `tenant_id` only |
| Storage | New tokens sealed into the same tenant’s `connector_secrets` |
| Audit | `connector.token_refreshed` / `connector.token_refresh_failed` (redacted) |
| Failure | Marks that connector `error` / needs re-auth — never other tenants |

Inline sync also calls the same refresh helper before broker pulls.
