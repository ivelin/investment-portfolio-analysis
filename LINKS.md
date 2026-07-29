# Project shortcuts

| What | Link |
|------|------|
| **Repo** | https://github.com/ivelin/investment-portfolio-analysis |
| **Branch** | `feature/multi-tenant-platform` |
| **PR** | https://github.com/ivelin/investment-portfolio-analysis/pull/5 |
| **Published app** | https://ivesting-portfolio-analysis.grok.me |
| **Handoff** | [HANDOFF.md](./HANDOFF.md) |
| **Web app source** | [web/](./web/) |
| **Architecture** | [docs/MULTI_TENANT_ARCHITECTURE.md](./docs/MULTI_TENANT_ARCHITECTURE.md) |
| **Security** | [docs/MULTI_TENANT_SECURITY.md](./docs/MULTI_TENANT_SECURITY.md) |

## Published login status
Auth providers are live on the published host. Neon wiring is in app code. Confirm with:

`GET https://ivesting-portfolio-analysis.grok.me/api/v1/health/auth`

Expect `database: "neon"` and `ok: true` once durable storage is attached (platform `DATABASE_URL` or sandbox bootstrap on republish). Preview uses PGLite and works without Neon.
