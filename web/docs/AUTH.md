# Authentication (Vercel + multi-tenant)

## Product path: Google + X only (no email/password)

Self-hosted **Better Auth** on this app’s origin (`/api/auth/*`) with built-in
**socialProviders**:

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

- Production: `https://investment-portfolio-analysis.vercel.app/api/auth/callback/google`
- Preview: each `*.vercel.app` host (or a stable preview domain if the provider
  allows only fixed URLs)

Also set **Authorized JavaScript origins** for the app origin(s).

### Other env (already used)

| Variable | Purpose |
|----------|---------|
| `BETTER_AUTH_SECRET` | Session signing (required on Vercel) |
| `DATABASE_URL` | Neon Postgres (sessions + users) |
| `VITE_AUTH_ENABLED` | Set `false` only to disable sign-in UI |
| `VERCEL_URL` | Auto on Vercel; used when `BETTER_AUTH_URL` is unset |

Do **not** set Grok broker secrets for Vercel. Do **not** commit OAuth secrets.

## Backend selection (shipped)

See `src/lib/auth/social-config.ts`:

| Condition | Mode |
|-----------|------|
| `VITE_AUTH_ENABLED=false` | disabled |
| `GOOGLE_*` and/or `TWITTER_*` set | **direct_social** (product path) |
| `VERCEL=1` without social env | **unconfigured** (fail closed — never Grok) |
| Non-Vercel without social env | **grok_broker** (legacy local / Grok sandbox only) |

Vercel hosts **never** fall through to `auth.grok.me` / `grok_preview`.

## Grok broker (legacy)

Only for non-Vercel Grok sandbox / local when direct social env is absent.
Not the production Vercel path.

## Health

`GET /api/v1/health/auth` reports `mode: "direct_social" | "unconfigured" | …`
without secrets.
