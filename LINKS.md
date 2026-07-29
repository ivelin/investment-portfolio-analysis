# Project shortcuts

| What | Link |
|------|------|
| **Repo** | https://github.com/ivelin/investment-portfolio-analysis |
| **Branch** | `feature/multi-tenant-platform` |
| **PR** | https://github.com/ivelin/investment-portfolio-analysis/pull/5 |
| **Published app** | https://investment-portfolio-analysis.grok.me |
| **Handoff** | [HANDOFF.md](./HANDOFF.md) |
| **Web app source** | [web/](./web/) |
| **Architecture** | [docs/MULTI_TENANT_ARCHITECTURE.md](./docs/MULTI_TENANT_ARCHITECTURE.md) |
| **Security** | [docs/MULTI_TENANT_SECURITY.md](./docs/MULTI_TENANT_SECURITY.md) |

## Published login status
Sign-in providers are configured. **App Neon wiring is done** (pool + migrations + auth). Production needs the host to inject `DATABASE_URL` on republish — check `GET /api/v1/health/auth` for `database: "neon"`. Preview uses PGLite and works without it.
