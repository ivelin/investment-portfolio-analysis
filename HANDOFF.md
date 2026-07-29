# Handoff — multi-tenant portfolio platform

## Remote
- Repo: https://github.com/ivelin/investment-portfolio-analysis
- Branch: `feature/multi-tenant-platform`
- PR: https://github.com/ivelin/investment-portfolio-analysis/pull/5

## Layout
| Path | What |
|------|------|
| `src/portfolio_analysis/` | Original Python MCP / CLI (local skill — defer unless asked) |
| `docs/` | Multi-tenant architecture, security, broker OAuth |
| `web/` | Hosted TanStack Start app (auth, tenants, brokers, legal, MCP API) |

Work in **`web/`** for the hosted product. Do not create a parallel app at repo root.

## Published app
- **URL:** https://ivesting-portfolio-analysis.grok.me  
  (slug is `ivesting-…`; `investment-portfolio-analysis.grok.me` is a different/dead slug)
- Stack: Grok App Builder (preview = PGLite, prod = Neon Postgres)
- Auth client **OK** on published host (`deployed_client` + `BETTER_AUTH_*`)
- Health: `GET /api/v1/health/auth` (secret-free)

### Login / Neon status (2026-07-29)
| Item | Status |
|------|--------|
| `GROK_AUTH_*` / `BETTER_AUTH_*` | Injected on published host |
| Platform `DATABASE_URL` | **Still not injected** by Grok publish |
| App Neon wiring | Done: dual-mode `getSql`/`getPgPool`, runtime migrations, auth shares pool |
| Serverless without DB | Fail closed (no PGLite WASM crash on Vercel) |
| Host-kind false positive | Fixed: live preview with `*.grok.me` Host still uses PGLite safely |
| Sandbox Neon bootstrap | Optional gitignored `web/src/lib/db-bootstrap.secret.ts` used **only on serverless** when env is missing (never commit) |
| Neon schema | Migrated on agent-provisioned Neon (`0001`–`0006`) when bootstrap is present |

## Product rules (non-negotiable)
1. Multi-tenant isolation — no shared portfolio/broker data across tenants; OAuth state user must match session; tenant only from server-side state
2. Self-management only — not investment advice; not RIA tooling
3. UX — no env-var dumps / PKCE jargon on product screens; path-to-success CTAs
4. Public repo hygiene — no secrets, balances, PII, real statements in git
5. Every PR — tests + green CI; DRY/MECE; fail closed

## Next steps (priority)
1. **Republish from Grok** with sandbox present so bootstrap (or platform `DATABASE_URL`) lands on the host — then confirm health shows `database: "neon"` and Google/X login works
2. Prefer platform-injected `DATABASE_URL` over bootstrap when available; delete bootstrap once host injects Neon
3. Continue per-tenant broker OAuth / portfolio features under `web/`
4. Do not re-scaffold, create parallel apps, or new feature branches unless asked

## Commands (web app)
```bash
cd web
npm install   # if needed
npm run dev   # 0.0.0.0:8080
npm run ci    # typecheck + tests
npm run build # production build + migrate when DATABASE_URL set
```

## Key web modules
| Area | Path |
|------|------|
| DB dual-mode | `web/src/lib/db.ts`, `web/src/lib/db-url.ts`, `web/src/lib/runtime-env.ts` |
| Auth server | `web/src/lib/auth/server.ts` |
| Auth health | `web/src/lib/auth/auth-runtime-status.ts`, `web/src/routes/api/v1/health/auth.ts` |
| Login UX | `web/src/routes/login.tsx` |
| Migrations | `web/migrations/*.sql` |
| Portfolio / brokers | `web/src/lib/portfolio/` |

## Standing rules
- Multi-tenant isolation; OAuth session bind
- Self-management only; not investment advice
- UI is not technical documentation
- Never commit `**/db-bootstrap.secret.ts` or real connection strings
