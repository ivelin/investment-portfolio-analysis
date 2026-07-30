# Handoff — multi-tenant portfolio platform

**Status date:** 2026-07-30

## Remote

- Repo: https://github.com/ivelin/investment-portfolio-analysis
- **Active branch:** `main`
- Naming: **investment-portfolio-analysis** on GitHub, Vercel, and Neon
- History: PR #5 multi-tenant land; PR #6 Vercel previews + social auth; later docs PRs

## Hosting decision (current truth)

| Target | Role | Status (2026-07-30) |
|--------|------|---------------------|
| **Vercel + Neon** | **Production path** | Live deploy + Neon `DATABASE_URL` + `BETTER_AUTH_SECRET`. Social login **blocked** until `GOOGLE_*` / `TWITTER_*` are set on the Vercel project. |
| **Grok App Build publish** (`*.grok.me`) | **Not product** | Broken: platform does not inject `DATABASE_URL`; Grok Build CLI cannot configure grok.me auth or Neon for this app. **Revisit ~mid–late Aug 2026** to see if Grok App Publish + CLI handoff improved. |
| **Grok sandbox / CLI preview** (`*.grok-sandbox.com`) | Agent live preview only | Optional **Grok broker** (`auth.grok.me`, `grok_preview`) when no direct social env; absolute `redirect_uri` required (fixed in app). |

**Do not** treat `*.grok.me` as production. Product login is **direct Google + X** via Better Auth on the app origin (`/api/auth/*`), never the Grok broker on Vercel.

Prod URL (project alias):

https://investment-portfolio-analysis-ivelins-projects-9f9b7132.vercel.app

Health: `GET {host}/api/v1/health/auth` — want `mode: "direct_social"`, `database: "neon"`, `publishLikelyBroken: false`.

## Auth product truth

See [web/docs/AUTH.md](web/docs/AUTH.md).

| Backend | When |
|---------|------|
| **direct_social** | `GOOGLE_*` and/or `TWITTER_*` set → Better Auth `socialProviders` |
| **grok_broker** | Non-Vercel only, no social env (sandbox/CLI) → `genericOAuth` → `auth.grok.me` |
| **unconfigured** | Vercel without social env (**fail closed** — never silent Grok) |

Email/password is **off**.

### Invalid redirect URI (fixed in code)

Grok broker was receiving relative `redirect_uri=/oauth2/callback/twitter` → `{"message":"Invalid redirect URI"}`.

App now:

1. Dynamic `baseURL` from Host / trusted proxy headers
2. Rewrites authorize URLs so `redirect_uri` is absolute (`oauth-redirect.ts`, server hook, client, popup)

```text
https://<preview-host>/api/auth/oauth2/callback/twitter
```

### Vercel OAuth callbacks (register in Google / X developer consoles)

```text
https://<deployment-host>/api/auth/callback/google
https://<deployment-host>/api/auth/callback/twitter
```

Also authorize JS origins for each host (or use a stable production domain).

### Blocker for end-to-end X login

As of 2026-07-30 prod health:

- `database: "neon"` ✓
- `hasStableSecret: true` ✓
- `mode: "unconfigured"` — **missing `GOOGLE_CLIENT_ID/SECRET` and/or `TWITTER_CLIENT_ID/SECRET` on Vercel**

Until those env vars are set on the Vercel project (Preview + Production), sign-in buttons stay disabled on Vercel and full X OAuth cannot be verified.

## Grok App / Build CLI — revisit window

**Parked until ~mid–late August 2026 (1–2 weeks from 2026-07-30).**

Check then whether:

1. Grok App **production Publish** injects durable `DATABASE_URL` (Neon or equivalent)
2. Grok Build **CLI** can configure or pass through OAuth / env for published `*.grok.me` hosts
3. Broker `redirect_uri` / preview client still matches sandbox hosts

Until then: ship and operate on **Vercel + Neon + direct Google/X only**.

## Layout

| Path | What |
|------|------|
| `web/` | Entire product: TanStack Start app, auth, tenants, brokers, legal, REST + MCP |
| `docs/` | Architecture, security, broker OAuth, product design |
| `scripts/git-hooks/` | pre-push → `make ci` |
| `startup.sh` | Sandbox revive: start `web` on `0.0.0.0:8080` |

## Stack

- **UI/API/MCP:** one deployable under `web/`
- **Domain SSOT:** `web/src/lib/portfolio/service.server.ts`
- **Auth:** Better Auth socialProviders (Google + X) on Vercel; Grok broker only non-Vercel without social env
- **DB:** Neon on Vercel; PGLite for local `npm run dev` only
- **CI:** GitHub Actions `web` + `vercel-deploy` + local `make ci` (coverage ≥80%)

## Commands

```bash
cd web && npm ci && npm run dev    # local (PGLite)
cd web && npm run ci               # typecheck + suites + coverage ≥80% + e2e
make ci                            # same from repo root (pre-push)
make install-hooks                 # pre-push runs make ci
```

Coverage: [web/docs/COVERAGE.md](web/docs/COVERAGE.md). CI/CD: [web/docs/CICD.md](web/docs/CICD.md).

## Product rules

1. Multi-tenant isolation; OAuth session bind
2. Self-management only — not investment advice
3. No secrets or PII in git
4. UI + REST + MCP share `service.server.ts` (no duplicate domain logic)
5. Green CI before push/merge

## Next steps

1. **Set Vercel env (required for login):** `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `TWITTER_CLIENT_ID`, `TWITTER_CLIENT_SECRET` (Preview + Production); register callback URLs above
2. Redeploy / merge so health reports `mode: "direct_social"`
3. Manually complete Sign in with X on prod; confirm session + dashboard
4. Optional: `VERCEL_AUTOMATION_BYPASS_SECRET` for full CI health under Deployment Protection
5. **~mid–late Aug 2026:** re-evaluate Grok App Publish + Build CLI (see section above)
6. Continue broker OAuth connectors and portfolio engines in `web/`
