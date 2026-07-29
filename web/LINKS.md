# Project shortcuts

Easy reference links for this multi-tenant portfolio analysis work.

## App (this build)

| What | Link |
|------|------|
| **Live preview** | Grok chat **outside** a Project → live preview panel (`*.grok-sandbox.com`) |
| **In-app links page** | `/links` in the preview |
| **Published app** | Your deploy URL (e.g. `*.grok.me`) — set here when stable |

### Sign-in: preview vs published

| Environment | Why login works / fails |
|-------------|-------------------------|
| **Preview** (`*.grok-sandbox.com`) | Shared sandbox OAuth client — works out of the box |
| **Published** (`*.grok.me`, etc.) | Needs **platform-injected** per-app auth: `GROK_AUTH_CLIENT_ID`, `GROK_AUTH_CLIENT_SECRET`, `BETTER_AUTH_URL` (or `APP_PUBLIC_URL`), `BETTER_AUTH_SECRET`, `DATABASE_URL` |

If login works in preview but not published, the deploy is almost always missing those env vars (preview client only allows sandbox callback URLs).

## Source & PR

| What | Link |
|------|------|
| **GitHub repo** | [ivelin/investment-portfolio-analysis](https://github.com/ivelin/investment-portfolio-analysis) |
| **Feature branch** | `feature/multi-tenant-platform` |
| **Pull request** | [PR #5](https://github.com/ivelin/investment-portfolio-analysis/pull/5) |
| **LINKS.md on GitHub** | [blob/.../LINKS.md](https://github.com/ivelin/investment-portfolio-analysis/blob/feature/multi-tenant-platform/LINKS.md) |

## Product pages (in the app)

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

## Docs (repo)

| Doc | Path |
|-----|------|
| Architecture | `docs/MULTI_TENANT_ARCHITECTURE.md` |
| Security | `docs/MULTI_TENANT_SECURITY.md` |
| Broker OAuth | `docs/BROKER_OAUTH.md` |

