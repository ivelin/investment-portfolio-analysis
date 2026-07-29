# Handoff — multi-tenant portfolio platform

## Remote

- Repo: https://github.com/ivelin/investment-portfolio-analysis
- Branch: `feature/multi-tenant-platform`
- PR: https://github.com/ivelin/investment-portfolio-analysis/pull/5
- Naming: **investment-portfolio-analysis** on GitHub, Vercel, and Neon

## Layout (multi-tenant only)

| Path | What |
|------|------|
| `web/` | Entire product: TanStack Start app, auth, tenants, brokers, legal, REST + MCP |
| `docs/` | Architecture, security, broker OAuth, product design |
| `scripts/git-hooks/` | pre-push → `make ci` |

There is **no** single-user Python CLI/MCP stack in this repository.

## Stack

- **UI/API/MCP:** one deployable under `web/`
- **Domain SSOT:** `web/src/lib/portfolio/service.server.ts`
- **Auth:** Better Auth + platform broker; `requireApiPrincipal` for REST/MCP
- **DB:** Neon on Vercel; PGLite for local `npm run dev` only
- **CI:** GitHub Actions `web` job + local `make ci`

## Commands

```bash
cd web && npm ci && npm run dev    # local
cd web && npm run ci               # typecheck + suites + coverage ≥80% + e2e
make ci                            # same from repo root (pre-push)
make install-hooks                 # pre-push runs make ci
```

Coverage policy: [web/docs/COVERAGE.md](web/docs/COVERAGE.md). Tests live under
`web/scripts/test-*.mjs` (domain) and `web/tests/{api,mcp,e2e}/`.

## Product rules

1. Multi-tenant isolation; OAuth session bind
2. Self-management only — not investment advice
3. No secrets or PII in git
4. UI + REST + MCP share `service.server.ts` (no duplicate domain logic)
5. Green CI before push/merge

## Next steps

1. Deploy to Vercel + Neon with `DATABASE_URL` + `BETTER_AUTH_*`
2. Verify `GET /api/v1/health/auth` → Neon-backed status
3. Continue broker OAuth and portfolio engines in `web/`
