# Authentication

## Product path: Google + X on Vercel (no email/password)

Self-hosted **Better Auth** on this app’s origin (`/api/auth/*`) with built-in
**socialProviders** when `GOOGLE_*` / `TWITTER_*` are set.

| Provider | Better Auth id | Env vars |
|----------|----------------|----------|
| Google | `google` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| X | `twitter` | `TWITTER_CLIENT_ID`, `TWITTER_CLIENT_SECRET` |

Email/password remains **disabled** (`email-password.ts`).

### Callback URLs (register in each OAuth app)

```text
https://<your-deployment-host>/api/auth/callback/google
https://<your-deployment-host>/api/auth/callback/twitter
```

Examples:

- Production alias: `https://investment-portfolio-analysis-ivelins-projects-9f9b7132.vercel.app/api/auth/callback/twitter`
- Preview: each `*.vercel.app` host (or a stable preview domain if the provider allows only fixed URLs)

Also set **Authorized JavaScript origins** for the app origin(s).

### Other env

| Variable | Purpose |
|----------|---------|
| `BETTER_AUTH_SECRET` | Session signing (required on Vercel) |
| `DATABASE_URL` | Neon Postgres (sessions + users) |
| `VITE_AUTH_ENABLED` | Set `false` only to disable sign-in UI |
| `VERCEL_URL` | Auto on Vercel; used when `BETTER_AUTH_URL` is unset |

Do **not** set Grok broker secrets for Vercel. Do **not** commit OAuth secrets.

## Backend selection (`social-config.ts`)

| Condition | Mode |
|-----------|------|
| `VITE_AUTH_ENABLED=false` | disabled |
| `GOOGLE_*` / `TWITTER_*` present | **direct_social** |
| `VERCEL=1` without social env | **unconfigured** (never silent Grok) |
| `AUTH_DISABLE_GROK_BROKER=true` | **unconfigured** |
| Else (Grok sandbox / CLI / local) | **grok_broker** |

| Backend | How |
|---------|-----|
| **direct_social** | Better Auth `socialProviders` → Google / X on this origin |
| **grok_broker** | Better Auth `genericOAuth` → `auth.grok.me` (sandbox/CLI only) |
| **unconfigured** | Fail closed — login UI explains missing config |

## Grok broker (sandbox / CLI only — not product)

Uses shared preview client (`grok_preview`) unless the platform injects
`GROK_AUTH_CLIENT_ID` / `GROK_AUTH_CLIENT_SECRET` (published `*.grok.me`).

Broker-allowed callback (preview client):

```text
https://*.grok-sandbox.com/api/auth/oauth2/callback/*
```

**Critical:** `redirect_uri` must be **absolute**. A relative
`/oauth2/callback/twitter` produces `Invalid redirect URI` on
`auth.grok.me`. This app:

1. Resolves dynamic `baseURL` from `Host` / `x-forwarded-host` (trusted proxy headers on)
2. Rewrites authorize URLs so `redirect_uri` is absolute (`oauth-redirect.ts` + server hook + popup + client)

Live preview opens OAuth in a **popup** (`/auth/popup`) so first-party cookies work inside the iframe.

### Grok App Publish — deferred

`*.grok.me` publish remains non-product: no platform `DATABASE_URL`, and Grok
Build CLI cannot configure grok.me auth for this app. **Revisit mid–late
August 2026** (see root [HANDOFF.md](../../HANDOFF.md)). Until then operate on
Vercel + Neon + direct social only.

## Health

`GET /api/v1/health/auth`

| Environment | Expect |
|-------------|--------|
| Grok sandbox / CLI (no social env) | `mode: "preview_client"`, `database: "pglite"` |
| Vercel + social + Neon | `mode: "direct_social"`, `database: "neon"`, `publishLikelyBroken: false` |
| Vercel without social | `mode: "unconfigured"`, issues list social env |

## Opt-out

`AUTH_DISABLE_GROK_BROKER=true` — disable broker fallback on non-Vercel hosts.
