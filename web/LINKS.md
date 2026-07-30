# Project shortcuts

Easy reference links for this multi-tenant portfolio analysis work.

## Hosting status (2026-07-30)

| Target | Status |
|--------|--------|
| **Vercel + Neon** | **Production path.** Project live; Neon + secret OK; set `GOOGLE_*` / `TWITTER_*` for social login. |
| **Grok App Build** `*.grok.me` | **Not product.** Publish/CLI gaps (no durable DB from platform). **Revisit mid–late Aug 2026.** |

~~https://ivesting-portfolio-analysis.grok.me~~ — not a supported live target.

| What | Link |
|------|------|
| **Vercel prod (alias)** | https://investment-portfolio-analysis-ivelins-projects-9f9b7132.vercel.app |
| **Local / CLI preview** | `cd web && npm run dev` → http://localhost:8080 |
| **In-app links page** | `/links` when the app is running |

### Sign-in environments

| Environment | Auth path |
|-------------|-----------|
| **Local** (`localhost:8080`) | PGLite; Grok broker if no social env, or direct Google/X if `GOOGLE_*`/`TWITTER_*` set |
| **Grok sandbox** (`*.grok-sandbox.com`) | Grok broker (`auth.grok.me`) by default; absolute `redirect_uri` fixed in app |
| **Grok published** (`*.grok.me`) | Not product — needs platform `DATABASE_URL` (revisit later) |
| **Vercel** | **Direct Google/X only** + Neon; never falls through to `auth.grok.me` |

Health (any host): `GET /api/v1/health/auth` — want `mode: "direct_social"` and `database: "neon"` on real deploys.

Full auth docs: [docs/AUTH.md](docs/AUTH.md). Ops handoff: [../HANDOFF.md](../HANDOFF.md).

## Source & PR

| What | Link |
|------|------|
| **GitHub repo** | [ivelin/investment-portfolio-analysis](https://github.com/ivelin/investment-portfolio-analysis) |
| **Default branch** | [`main`](https://github.com/ivelin/investment-portfolio-analysis/tree/main) |
| **Coverage policy** | [docs/COVERAGE.md](docs/COVERAGE.md) |
| **CI/CD** | [docs/CICD.md](docs/CICD.md) |

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
