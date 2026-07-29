# Project shortcuts

Easy reference links for this multi-tenant portfolio analysis work.

## App (this build)

| What | Link |
|------|------|
| **Live preview** | Grok chat **outside** a Project → live preview panel (`*.grok-sandbox.com`) |
| **In-app links page** | `/links` in the preview |
| **Published app** | https://ivesting-portfolio-analysis.grok.me |

### Sign-in: preview vs published

| Environment | Why login works / fails |
|-------------|-------------------------|
| **Preview** (`*.grok-sandbox.com`) | Shared sandbox OAuth client — works out of the box (PGLite) |
| **Published** (`*.grok.me`) | Needs `GROK_AUTH_*`, `BETTER_AUTH_*`, and durable Postgres (`DATABASE_URL` / Neon) |

**Current:** Auth client configured (`deployed_client`). App Neon path complete. Health: `GET /api/v1/health/auth` → want `database: "neon"`.

## Source & PR

| What | Link |
|------|------|
| **GitHub repo** | [ivelin/investment-portfolio-analysis](https://github.com/ivelin/investment-portfolio-analysis) |
| **Feature branch** | `feature/multi-tenant-platform` |
| **Pull request** | [PR #5](https://github.com/ivelin/investment-portfolio-analysis/pull/5) |

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
