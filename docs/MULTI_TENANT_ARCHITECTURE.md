# Multi-tenant platform architecture (Phase 1)

**Branch:** `feature/multi-tenant-platform`  
**Goal:** Extend the local-first MCP/CLI skill into a **hosted multi-tenant** app
(web + API + MCP + auth + scalable Postgres) without ever committing personal
financial data to this public repository.

## Modes

| Mode | Data home | Auth | Audience |
|------|-----------|------|----------|
| **Local skill** (existing) | `~/.investment-portfolio-analysis/` SQLite | Operator machine | Single user / agent |
| **Hosted platform** (this work) | Neon Postgres (PGLite in preview) | Better Auth → Grok broker (Google / X) | Many tenants |

The local skill remains fully supported. Hosted does **not** replace local-first;
it reuses the same analytical philosophy (ground truth vs derived, no fabricated
history) behind a multi-tenant boundary.

## Components

```text
Browser (grok.me app)
  └─ Session (Better Auth / Grok broker)
       ├─ Dashboard (server fns, tenant-scoped SQL)
       ├─ REST  /api/v1/portfolio/*
       └─ MCP   /api/v1/mcp   (JSON tools, same auth)

Postgres (Neon)
  auth tables (Better Auth)
  tenants / tenant_members
  broker_accounts (opaque account_key)
  gt_* ground truth + fund_daily derived
  connector_secrets (ciphertext only)
  audit_events (redacted meta)
```

## Tenant model

1. On first authenticated request, provision a **personal workspace** (`tenants` +
   `tenant_members.role = owner`).
2. Every portfolio row carries `tenant_id`.
3. Server paths call `requireTenantAccess(userId, tenantId, minRole)` before
   reads/writes.
4. Never trust a client-supplied user id or tenant id without membership check.

## Data integrity (unchanged philosophy)

- Prefer incomplete truth over comforting fiction.
- Demo / synthetic data is explicitly labeled (`is_demo`, source=`demo`).
- Hosted Phase 1 ships synthetic demo funds so the product is usable without
  real broker credentials.
- Live broker OAuth and export upload are later phases; secrets go only into
  `connector_secrets` ciphertext, never into git or API dumps.

## API / MCP

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/portfolio/summary` | Session-auth workspace summary |
| `GET/POST /api/v1/mcp` | Tool catalog + tenant-scoped tools |

MCP tools in Phase 1: `list_tools`, `workspace_summary`, `positions`, `fund_series`.

## Security hard rules

See [MULTI_TENANT_SECURITY.md](./MULTI_TENANT_SECURITY.md) and root
[SECURITY.md](../SECURITY.md).

## Phased delivery

| Phase | Scope |
|-------|--------|
| **1** (this branch / grok-build) | Auth, tenant schema, demo fund dashboard, REST + MCP stub, redaction helpers |
| **2** | Export upload (tenant-scoped object storage), parse → `gt_*` |
| **3** | Broker OAuth connectors (encrypted secrets), sync jobs |
| **4** | Port TWRR / weed-the-garden engines; fund-as-symbol alerts |
| **5** | Collaborators, plans/billing, audit UI |

## Relationship to Python package

`src/portfolio_analysis/` remains the local skill SSOT. Hosted TypeScript reuses
concepts (fund symbol, GT tables, redaction) but runs as a separate deployable
with Neon. Over time, pure calculation modules may be shared via documented
parity tests — never by committing instance databases.
