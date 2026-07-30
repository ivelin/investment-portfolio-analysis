# Handoff — multi-tenant portfolio platform

## Remote

- Repo: https://github.com/ivelin/investment-portfolio-analysis
- **Active branch:** `main` (multi-tenant product + Vercel/Neon CI + Google/X social auth)
- Historical: PR #5 multi-tenant land; PR #6 Vercel previews + social auth
- Naming: **investment-portfolio-analysis** on GitHub, Vercel, and Neon

## Layout (multi-tenant only)

| Path | What |
|------|------|
| `web/` | Entire product: TanStack Start app, auth, tenants, brokers, legal, REST + MCP |
| `docs/` | Architecture, security, broker OAuth, product design |
| `scripts/git-hooks/` | pre-push → `make ci` |

There is **no** single-user Python CLI/MCP stack in this repository.

## Deployments

| Host | URL | DB | Auth | Login |
|------|-----|----|------|-------|
| **Vercel + Neon (prod path)** | https://investment-portfolio-analysis-ivelins-projects-9f9b7132.vercel.app (and project aliases) | **Neon** when Marketplace / env injects `DATABASE_URL` | Better Auth **direct Google + X** (`GOOGLE_*` / `TWITTER_*`); **not** Grok broker | Durable sessions when Neon + social env set; email/password **off** |
| **Grok publish** | https://ivesting-portfolio-analysis.grok.me | **No `DATABASE_URL`** (platform gap) | Grok injects `GROK_AUTH_*` but app still needs a DB for sessions | **Broken** until host injects Neon — agents cannot set `*.grok.me` env |

Health checks:

- `GET {host}/api/v1/health/auth`
- `GET {host}/api/auth/ok`

Auth product truth (do not regress): [web/docs/AUTH.md](web/docs/AUTH.md) — Google + X only; no email/password; Vercel never falls through to `auth.grok.me`. CI/deploy: [web/docs/CICD.md](web/docs/CICD.md).

## Why grok.me stays broken

Grok injects `GROK_AUTH_*` + `BETTER_AUTH_*` but **not** `DATABASE_URL` for this app.
Serverless cannot use PGLite across OAuth redirects. App code fail-closes cleanly
(`AUTH_NO_DATABASE`) instead of crashing on missing WASM.

Gitignored sandbox bootstrap (`web/src/lib/db-bootstrap.secret.ts`) only helps if
the **Grok build includes that sandbox file**. Builds from public git alone never
ship it (and must not — secrets). Prefer platform-injected `DATABASE_URL`.

**Do not** treat adding `GROK_AUTH_*` on Vercel as the primary login fix. Vercel
login is **direct Google/X** + Neon (`DATABASE_URL` + `BETTER_AUTH_SECRET` +
`GOOGLE_*` / `TWITTER_*`). See AUTH.md.

## Stack

- **UI/API/MCP:** one deployable under `web/`
- **Domain SSOT:** `web/src/lib/portfolio/service.server.ts`
- **Auth:** Better Auth socialProviders (Google + X) on Vercel; Grok broker only for non-Vercel local/sandbox when social env is absent; `requireApiPrincipal` for REST/MCP
- **DB:** Neon on Vercel; PGLite for local `npm run dev` only
- **CI:** GitHub Actions `web` + `vercel-deploy` + local `make ci` (coverage ≥80%)

## Commands

```bash
cd web && npm ci && npm run dev    # local (PGLite)
cd web && npm run ci               # typecheck + suites + coverage ≥80% + e2e
make ci                            # same from repo root (pre-push)
make install-hooks                 # pre-push runs make ci
```

Coverage policy: [web/docs/COVERAGE.md](web/docs/COVERAGE.md). Tests live under
`web/scripts/test-*.mjs` (domain) and `web/tests/{api,mcp,e2e}/`.

## Product rules

1. Multi-tenant isolation; OAuth session bind
2. Self-management only — not investment advice
3. No secrets or PII in git
4. UI + REST + MCP share `service.server.ts` (no duplicate domain logic)
5. Green CI before push/merge

## Next steps

1. **Vercel prod login:** set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` and
   `TWITTER_CLIENT_ID` / `TWITTER_CLIENT_SECRET` (plus existing Neon +
   `BETTER_AUTH_SECRET`); register OAuth callback URLs per AUTH.md
2. **Optional CI:** `VERCEL_AUTOMATION_BYPASS_SECRET` for full health under
   Deployment Protection (see CICD.md)
3. **Grok.me (optional / legacy):** needs platform `DATABASE_URL` on
   `ivesting-portfolio-analysis.grok.me` — not fixable from public git alone
4. Continue broker OAuth and portfolio engines in `web/`
