# Per-tenant broker OAuth design

Financial data. **Every user OAuth token is tenant-scoped.**

## Auth models (do not conflate)

| Broker | Auth model | Linking | Data pull |
|--------|------------|---------|-----------|
| **Schwab** | Direct Developer API OAuth (PKCE + confidential client) | Schwab Developer app; user authorizes `readonly` | REST Trader API with user access token |
| **Robinhood** | Remote MCP OAuth 2.1 (public client + DCR) | Hosted MCP `https://agent.robinhood.com/mcp/trading` | MCP tools with user access token |
| **Interactive Brokers** | Remote MCP OAuth 2.1 (public client + DCR) | Hosted MCP `https://api.ibkr.com/v1/api/mcp-public` | MCP tools with user access token (`mcp.read`) |

Reference: local skill `portfolio_analysis/schwab/auth.py` (PKCE S256 + form token exchange).

## Isolation

1. Platform client credentials ≠ user tokens.
2. OAuth `state` binds `tenant_id` + `user_id` (one-time).
3. Tokens sealed only under that tenant’s `connector_secrets`.
4. No shared platform snapshot for multi-tenant Connect.
5. Never log tokens or raw account numbers.

## Token refresh job

Job id: `token_refresh`.

- Refresh when `expires_at - now < skew` (default 10 minutes) or `force`.
- Process one connector at a time with its own `tenant_id`.
- On refresh failure with invalid_grant → mark connector needs re-auth.
- Audit events redacted; never return tokens from job APIs.

Decision helper (must stay MECE):

- no access token → `needs_reauth`
- not due and not force → `skip`
- due/force without refresh_token → `needs_reauth`
- due/force with refresh_token → `refresh`

## Path to success (product UX)

1. User opens Connect → if app credentials missing, show setup guide (never a dead button).
2. Register callback URL: `/api/v1/oauth/{broker}/callback` on the broker developer portal.
3. Save app credentials (platform) then start user OAuth; callback exchanges code into **tenant-scoped** tokens only.
4. Dashboard and MCP read the same tenant boundary.
