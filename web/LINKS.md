# Project shortcuts

Easy reference links for this multi-tenant portfolio analysis work.

## Hosting status

| Target | Status |
|--------|--------|
| **Grok App Build** `*.grok.me` | **Not in use.** Hosted app path blocked pending Grok **CLI ↔ App Build handover**. Do not treat as prod. |
| **Vercel + Neon** | **Intended** production/preview stack. Project provisioned; CI deploys previews on PR (see [docs/CICD.md](docs/CICD.md)). |

~~https://ivesting-portfolio-analysis.grok.me~~ — stale; not a supported live target while handover is pending.

| What | Link |
|------|------|
| **Local / CLI preview** | `cd web && npm run dev` → http://localhost:8080 |
| **In-app links page** | `/links` when the app is running |

### Sign-in environments (when each host exists)

| Environment | Why login works / fails |
|-------------|-------------------------|
| **Local** (`localhost:8080`) | PGLite + preview auth client (or local env) |
| **Grok sandbox preview** (`*.grok-sandbox.com`) | Shared sandbox OAuth client + PGLite (when using App Build sandbox) |
| **Grok published** (`*.grok.me`) | Needs platform-injected `GROK_AUTH_*`, `BETTER_AUTH_*`, `DATABASE_URL` — **handover not available yet** |
| **Vercel** | Needs project env (`DATABASE_URL` Neon, `BETTER_AUTH_*`, etc.) after first deploy |

Health (any host): `GET /api/v1/health/auth` — want `database: "neon"` on real deploys.

## Source & PR

| What | Link |
|------|------|
| **GitHub repo** | [ivelin/investment-portfolio-analysis](https://github.com/ivelin/investment-portfolio-analysis) |
| **Default branch** | `main` (multi-tenant stack merged via PR #5) |
| **Coverage policy** | [docs/COVERAGE.md](docs/COVERAGE.md) |

## Product pages

| Page | Path |
|------|------|
| Home | `/` |
| Sign in | `/login` |
| Dashboard | `/dashboard` |
| Brokers | `/connectors` |
| Settings | `/settings` |
| Links | `/links` |
| Terms | `/terms` |
| Privacy | `/privacy` |
| Intended use | `/intended-use` |
| Security | `/security` |
