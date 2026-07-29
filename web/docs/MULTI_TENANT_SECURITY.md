# Multi-tenant security (public repository)

This repository is **public**. Hosted multi-tenant code must not weaken privacy
or leak one tenant’s portfolio into another.

## Never commit

- Anything under a local skill home / export folders
- Broker exports (CSV, XML, PDF), SQLite/Postgres dumps, report artifacts with balances
- OAuth tokens, client secrets, `.env` files, private keys, tenant API keys
- Unredacted account numbers, SSN/TIN, taxpayer names, addresses
- Screenshots or fixtures derived from **real** portfolios
- **Shared “live snapshots”** of any real broker session

## Hosted platform rules

1. **Tenant isolation** — every query filters by `tenant_id` after membership or
   API-key → tenant resolution. Never trust a client-supplied tenant id alone.
2. **No shared broker path** — platform/operator MCP OAuth must not feed a
   multi-tenant Connect button. Each tenant completes **their** OAuth.
3. **Opaque account keys** — never use raw brokerage account numbers as primary keys.
4. **Masking** — UI may show `…` + last 3 digits only.
5. **Secrets** — connector credentials encrypted at rest; never returned by APIs or MCP.
6. **API keys** — store SHA-256 only; prefix for display; revoke supported.
7. **Redaction** — log and audit payloads run through redaction helpers before write.
8. **Auth fail closed** — portfolio API/MCP require session or valid `pa_` key.
9. **No secrets in the worktree** — host injects `DATABASE_URL` / OAuth env at deploy.

## SOX-oriented control notes

We do not claim formal SOC 2 certification here. Engineering controls map to:

| Area | Practice |
|------|----------|
| Logical access | Auth + roles + tenant membership |
| Data isolation | `tenant_id` + service-layer enforcement |
| Monitoring | `audit_events` (redacted) |
| Confidentiality | Encryption envelope for connector secrets; redaction |
| Change management | Migrations, public code review, no PII in repo |

## Reporting a leak

1. Rotate affected credentials immediately.
2. Do **not** paste secrets into issues or chat.
3. Open a private security report describing path + commit SHA only.
4. History rewrite may be required for public git.

## Demo data

Synthetic demo portfolios are allowed. They must be labeled and must not be
reverse-engineered from real user balances.
