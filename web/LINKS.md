# Project shortcuts

Easy reference links for this multi-tenant portfolio analysis work.

## App (this build)

| What | Link |
|------|------|
| **Live preview** | Grok chat **outside** a Project → live preview panel (`*.grok-sandbox.com`) |
| **In-app links page** | `/links` in the preview |
| **Published app** | https://investment-portfolio-analysis.grok.me |

### Sign-in: preview vs published

| Environment | Why login works / fails |
|-------------|-------------------------|
| **Preview** (`*.grok-sandbox.com`) | Shared sandbox OAuth client — works out of the box (PGLite) |
| **Published** (`*.grok.me`, etc.) | Needs **platform-injected** per-app auth: `GROK_AUTH_CLIENT_ID`, `GROK_AUTH_CLIENT_SECRET`, `BETTER_AUTH_URL` (or `APP_PUBLIC_URL`), `BETTER_AUTH_SECRET`, **`DATABASE_URL`** |

**Current:** auth client is configured (`deployed_client`). **`DATABASE_URL` still missing** on production — check `GET /api/v1/health/auth`.

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
