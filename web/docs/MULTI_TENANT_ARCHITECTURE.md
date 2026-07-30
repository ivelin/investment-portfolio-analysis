# Multi-tenant platform architecture

**Branch:** `main`  
**Goal:** Hosted multi-tenant portfolio app (web + API + MCP + auth + Neon)
without ever committing personal financial data to this public repository.

This repository contains **only** the multi-tenant stack under `web/`.
Auth product path: Better Auth **Google + X** social on Vercel (see [AUTH.md](./AUTH.md)).

## Components

```text
Browser
  └─ Session (Better Auth social: Google + X on Vercel)
       ├─ Dashboard (server fns, tenant-scoped SQL)
       ├─ REST  /api/v1/portfolio/*
       └─ MCP   /api/v1/mcp   (JSON tools, same auth)

Postgres (Neon in deploy; PGLite in local dev)
  auth tables (Better Auth)
  tenants / tenant_members
  broker_accounts
  gt_* ground truth + fund_daily derived
  connector_secrets (ciphertext only)
  audit_events (redacted meta)
```

## Domain layer (DRY)

All product logic lives in `web/src/lib/portfolio/`, especially
`service.server.ts`.

| Surface | Adapter | Domain |
|---------|---------|--------|
| Web UI | Server functions (`queries.ts`, …) | `service.server.ts` |
| REST | `/api/v1/portfolio/*` + `api-auth.server.ts` | same |
| MCP | `/api/v1/mcp` + `api-auth.server.ts` | same |

Do **not** reimplement portfolio queries in routes or tools.

## Tenant model

1. On first authenticated request, provision a **personal workspace**
   (`tenants` + `tenant_members.role = owner`).
2. Every portfolio row carries `tenant_id`.
3. Server paths call membership checks before reads/writes.
4. Never trust a client-supplied user id or tenant id without verification.

## Data integrity

- Prefer incomplete truth over comforting fiction.
- Demo / synthetic data is explicitly labeled (`is_demo`, source=`demo`).
- Phase 1 ships synthetic demo funds so the product is usable without real
  broker credentials.
- Live broker OAuth and export upload are later phases; secrets go only into
  `connector_secrets` ciphertext.

## API / MCP

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/portfolio/summary` | Session or API-key workspace summary |
| `GET/POST /api/v1/mcp` | Tool catalog + tenant-scoped tools |
| `GET /api/v1/health/auth` | Secret-free deploy health |

MCP tools (Phase 1): `list_tools`, `workspace_summary`, `list_accounts`,
`positions`, `fund_series`, `list_connectors`.

Auth: session cookie **or** `Authorization: Bearer pa_…` (tenant API key).

## Security hard rules

See [MULTI_TENANT_SECURITY.md](./MULTI_TENANT_SECURITY.md) and root
[SECURITY.md](../SECURITY.md).

## Phased delivery

| Phase | Scope |
|-------|--------|
| **1** | Auth, tenant schema, demo fund dashboard, REST + MCP, redaction |
| **2** | Export upload (tenant-scoped storage), parse → `gt_*` |
| **3** | Broker OAuth connectors (encrypted secrets), sync jobs |
| **4** | TWRR / weed-the-garden engines on workspace data |
| **5** | Collaborators, plans/billing, audit UI |

## Per-broker OAuth

| Broker | Auth model | Notes |
|--------|------------|-------|
| Schwab | Developer API OAuth (PKCE + client secret) | App-level env; **user tokens per tenant** |
| Robinhood | Hosted MCP OAuth 2.1 + DCR | Resource-scoped |
| Interactive Brokers | Hosted MCP OAuth 2.1 + DCR | Resource-scoped |

**Hard rule:** never use a shared operator MCP session as a multi-tenant feed.
See [BROKER_OAUTH.md](./BROKER_OAUTH.md).

## SRE / CI

- **Green CI required** before merge: `web` typecheck + suite and `vercel-deploy` on PRs to `main`.
- Local: `make ci` (also enforced by pre-push hook).
- Fail closed on auth, tenant membership, and missing OAuth state.
- No secrets in git, fixtures, logs, or public API responses.
