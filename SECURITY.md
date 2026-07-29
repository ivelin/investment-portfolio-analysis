# Security and privacy

This repository is the **public source** for a **hosted multi-tenant** portfolio
platform. Real balances, broker tokens, and PII must never appear in git.

Also read:

- [docs/MULTI_TENANT_SECURITY.md](docs/MULTI_TENANT_SECURITY.md)
- [docs/MULTI_TENANT_ARCHITECTURE.md](docs/MULTI_TENANT_ARCHITECTURE.md)

## Where secrets live

| Kind | Location |
|------|----------|
| `DATABASE_URL` / Neon | Vercel project env (and Neon console) — not the repo |
| `BETTER_AUTH_SECRET`, auth broker vars | Vercel env |
| Broker OAuth client id/secret | Vercel env (`SCHWAB_*`, etc.) |
| User broker tokens | Encrypted in Postgres `connector_secrets` (per tenant) |
| Tenant API keys | Hashed in DB; raw key shown once at creation |

**Never** commit:

- `.env`, `.env.local`, `db-bootstrap.secret.ts`
- Connection strings, OAuth tokens, export files, balance-bearing reports
- Real account numbers or tax documents

## Multi-tenant hard rules

1. Every portfolio row is scoped by `tenant_id`.
2. Server paths resolve tenant from **session or API key**, never from a raw client claim alone.
3. Broker OAuth state is bound to the authenticated user; callback must match session.
4. Tool/API responses are redacted — no connector secrets or full account numbers.
5. Fail closed when auth, membership, or database config is missing (especially on Vercel without `DATABASE_URL`).

## Local development

- Use PGLite (default when `DATABASE_URL` is unset) or a personal Neon branch.
- Keep any real credentials only in ignored local env files or the Vercel/Neon consoles.
- `make ci` / `web` tests must not require production secrets.

## Reporting issues

If you find a security issue in this project, open a private report to the
maintainer rather than filing a public issue with exploit details or real data.
