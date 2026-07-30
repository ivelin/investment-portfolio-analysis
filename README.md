# Portfolio Analysis

**Hold yourself to the same standard you hold every stock.**

A **hosted multi-tenant** app for retail self-accountability: measure portfolio and
**per-account** performance with capital efficiency, keep / monitor / weed
discipline, and incomplete truth over comforting fiction.

## Product

| Capability | Description |
|------------|-------------|
| **Workspaces** | Personal tenant isolation — your data never mixes with another user’s |
| **Auth** | Better Auth social sign-in (Google + X); email/password off |
| **Dashboard** | Demo/synthetic funds first; real broker data via connectors |
| **API + MCP** | Same domain service as the UI — session or tenant API key |
| **Honest data** | No fabricated daily history; gaps are shown as incomplete |

## Stack

| Layer | Technology |
|-------|------------|
| App | TanStack Start, React 19, Vite, Nitro → Vercel |
| UI | Tailwind CSS 4, Radix UI |
| Auth | Better Auth (`/api/auth/*`) |
| Database | Neon Postgres (PGLite for local dev only) |
| Domain | `web/src/lib/portfolio/service.server.ts` (UI + REST + MCP) |
| Hosting | Vercel + Neon |

Application code lives entirely under **`web/`**.

## Quick start (developers)

```bash
cd web
npm ci
npm run dev          # http://localhost:8080
npm run ci           # typecheck + test suite (required before push)
```

Full local gate from repo root:

```bash
make ci              # web typecheck + suites
make install-hooks   # pre-push runs make ci
```

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/MULTI_TENANT_ARCHITECTURE.md](docs/MULTI_TENANT_ARCHITECTURE.md) | Tenants, API, MCP, Neon |
| [docs/MULTI_TENANT_SECURITY.md](docs/MULTI_TENANT_SECURITY.md) | Isolation + public-repo hard rules |
| [docs/BROKER_OAUTH.md](docs/BROKER_OAUTH.md) | Per-tenant broker OAuth |
| [web/docs/AUTH.md](web/docs/AUTH.md) | Google + X social auth (no email/password) |
| [web/docs/CICD.md](web/docs/CICD.md) | GitHub → Vercel + Neon previews |
| [SECURITY.md](SECURITY.md) | Secrets, redaction, no PII in git |
| [HANDOFF.md](HANDOFF.md) | Deploy / agent handoff |

## Principles (non-negotiable)

1. **Incomplete truth over comforting fiction** — never invent daily values to fill gaps.
2. **You cannot fire yourself — so measure yourself** — accounts are measured like funds.
3. **Tenant isolation** — no shared portfolio or broker secrets across workspaces.
4. **Public repo stays clean** — no real balances, tokens, exports, or PII in git.

## Status

Default branch: **[`main`](https://github.com/ivelin/investment-portfolio-analysis/tree/main)**  
(multi-tenant platform, Vercel/Neon CI, Google/X social auth — feature branch fully merged and deleted).

## License

Copyright 2025–2026 Ivelin Ivanov

Licensed under the **Apache License, Version 2.0**. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
