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

## Published app (blocked)
- URL: https://investment-portfolio-analysis.grok.me
- Auth client **OK** (`GROK_AUTH_*` present)
- **Missing `DATABASE_URL`** (Neon/Postgres) — login cannot work until platform injects it
- Preview works without Neon (PGLite)

## Next steps (priority)
1. Attach Neon / set `DATABASE_URL` on production → republish → verify Google/X login
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
