# Multi-tenant security (public repository)

This repository is **public**. Hosted multi-tenant code must not weaken the
local skill's privacy guarantees.

## Never commit

- Anything under `PORTFOLIO_ANALYSIS_HOME` / `~/.investment-portfolio-analysis/`
- Broker exports (CSV, XML, PDF), SQLite/Postgres dumps, report artifacts with balances
- OAuth tokens, client secrets, `.env` files, private keys
- Unredacted account numbers, SSN/TIN, taxpayer names, addresses
- Screenshots or fixtures derived from **real** portfolios

Tracked fixtures under `tests/fixtures/extractions/` must remain **synthetic**
(placeholder account `999-000001`, demo holdings only).

## Hosted platform rules

1. **Tenant isolation** — every query filters by `tenant_id` after membership check.
2. **Opaque account keys** — never use raw brokerage account numbers as primary keys.
3. **Masking** — UI may show `…` + last 3 digits only.
4. **Secrets** — connector credentials encrypted at rest; never returned by APIs or MCP.
5. **Redaction** — log and audit payloads run through redaction helpers before write.
6. **Auth** — portfolio API/MCP require a verified session; fail closed when signed out.
7. **No secrets in the worktree** — platform injects `DATABASE_URL` / auth env at deploy;
   do not create committed `.env` files with real values.

## Reporting a leak

1. Rotate affected credentials immediately.
2. Do **not** paste secrets into issues or chat.
3. Open a private security report describing path + commit SHA only.
4. History rewrite may be required for public git.

## Demo data

Synthetic demo portfolios are allowed in product and tests. They must be labeled
and must not be reverse-engineered from real user balances.

## Token refresh

Background token refresh must:

1. Load secrets only for the connector’s `tenant_id`.
2. Write refreshed tokens only to that same tenant.
3. Never batch tokens into a shared process cache keyed only by broker.
4. Log redacted outcomes only (`connector.token_refreshed` / `token_refresh_failed`).

## OAuth session bind (account-linking CSRF)

Callback must:

1. Load `broker_oauth_states` by `state` + broker (tenant from row only).
2. Require an authenticated browser session whose `user_id` equals `state.user_id`.
3. On mismatch: reject, audit `connector.oauth_bind_rejected`, do not seal tokens.
4. On match: one-shot consume state, seal tokens under that `tenant_id` only.

## Intended use (self-management)

- Retail investors analyzing **their own** accounts.
- **Not** investment advice.
- **Not** for RIAs / advisors / professional client services.
- Product must not ship features that manage third-party client money under one operator login without a separate approved product mode.

## Legal acceptance (minimal)

Before private product use, each user must accept a versioned **Terms + Privacy** pack (one click). Store `user_id`, document id, version, `accepted_at`. Bump version when text changes to re-prompt. Template language only — counsel review before commercial launch.
