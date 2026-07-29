# Multi-tenant security (public repository)

This repository is **public**. The product is **hosted multi-tenant only**.

## Never commit

- Broker exports (CSV, XML, PDF), DB dumps, report artifacts with balances
- OAuth tokens, client secrets, `.env` files, private keys
- Unredacted account numbers, SSN/TIN, taxpayer names, addresses
- Screenshots or fixtures derived from **real** portfolios
- `DATABASE_URL` or any connection string

## Hosted platform rules

1. **Tenant isolation** — every query filters by `tenant_id` after membership check.
2. **Opaque account keys** — never use raw brokerage account numbers as primary keys.
3. **Masking** — UI may show `…` + last 3 digits only.
4. **Secrets** — connector credentials encrypted at rest; never returned by APIs or MCP.
5. **Redaction** — log and audit payloads run through redaction helpers before write.
6. **Auth** — portfolio API/MCP require a verified session or tenant API key; fail closed.
7. **No secrets in the worktree** — Vercel/Neon inject env at deploy; do not commit `.env`.

## Reporting a leak

1. Rotate affected credentials immediately.
2. Do **not** paste secrets into issues or chat.
3. Open a private security report describing path + commit SHA only.
4. History rewrite may be required for public git.

## Demo data

Synthetic demo portfolios are allowed in product and tests. They must be labeled
and must not be reverse-engineered from real user balances.

## Token refresh

Tenant-scoped only. Open `connector_secrets` for that connector’s `tenant_id`
only. Failures mark only that connector — never another tenant.

## OAuth session bind

Broker OAuth start stores the authenticated user id in state. Callback rejects
mismatches. Tenant id for token storage comes from the server session, not the
client body.
