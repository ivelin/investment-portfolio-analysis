# Handoff — multi-tenant portfolio platform

## Remote
- Repo: https://github.com/ivelin/investment-portfolio-analysis
- Branch: `feature/multi-tenant-platform`
- PR: https://github.com/ivelin/investment-portfolio-analysis/pull/5

## Layout
| Path | What |
|------|------|
| `src/portfolio_analysis/` | Original Python MCP / CLI |
| `docs/` | Multi-tenant architecture, security, broker OAuth |
| `web/` | Hosted TanStack Start app (auth, tenants, brokers, legal) |

## Published app
- URL: https://investment-portfolio-analysis.grok.me
- Stack: Grok App Builder (preview = PGLite, prod = Neon via `DATABASE_URL`)
- Auth client **OK** (`GROK_AUTH_*` + `BETTER_AUTH_*` present on published host)
- **App Neon wiring is complete** in `web/` (shared pool, runtime migrations, auth awaits DB ready)
- Published host health still reports `database: pglite` until the **host injects `DATABASE_URL`** (agent cannot set env on `*.grok.me` from the sandbox)

## Neon wiring (agent-owned — no user action)
| Layer | Behavior |
|-------|----------|
| Preview | PGLite + `migrations/*.sql` on startup |
| Prod code | `getPgPool()` / `getSql()` when `DATABASE_URL` is set; max-1 serverless pool |
| Migrations | Build-time (`npm run db:migrate`) **and** runtime first connect (idempotent `_migrations`) |
| Auth | Better Auth uses the same Neon pool; `/api/auth/*` awaits `ensureAuthReady()` |
| Secrets | Never written to the worktree; platform injects on publish |

## Next steps (priority)
1. **Republish** the Grok app so the host attaches Neon (`DATABASE_URL`) — then verify `GET /api/v1/health/auth` shows `database: "neon"` and Google/X login works
2. Keep UI copy plain (no env dumps on login)
3. Per-tenant broker OAuth (Schwab/Robinhood) designed in `docs/` + `web/src/lib/portfolio/`
4. Do not commit secrets, real balances, or PII

## Commands (web app)
```bash
cd web
npm install   # if needed
npm run dev   # 0.0.0.0:8080
npm run ci    # typecheck + tests
```

## Standing rules
- Multi-tenant isolation; OAuth session bind
- Self-management only; not investment advice
- UI is not technical documentation
