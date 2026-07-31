# Platform bug report — Grok App publish environment incomplete

**To:** Grok App Builder / Deploy platform  
**From:** App Builder agent session (user: ivelini / SuperGrok Pro)  
**Date:** 2026-07-30  
**Severity:** **P0** for any app needing auth + persisted user data on `*.grok.me`  
**Product ask:** *“Provisioning of deployment environment should be transparent to the app builder.”*

---

## Summary

Publishing to `*.grok.me` does not fully provision the app environment. Two independent gaps:

| Gap | Symptom | Status on `arrow-meadow-birch-civic.grok.me` |
|-----|---------|-----------------------------------------------|
| **A. No durable Postgres** | `AUTH_NO_DATABASE`, health `database: pglite` | Mitigated agent-side with claimable Neon bootstrap (stopgap) |
| **B. OAuth client redirect URIs** | `{"message":"Invalid redirect URI"}` on `auth.grok.me` | **Open — platform must fix** |

App builders must not provision Neon accounts, claim neon.new into personal Vercel orgs, or patch broker client registration.

---

## Bug B — Invalid redirect URI (current user report)

**Confirmed 2026-07-30 21:09 UTC** with user URL including `idp=twitter`, clean cookies, and fresh Mozilla: still `Invalid redirect URI`.

Agent clean browser reaches `x.com` authorize **before** IdP login. Failure occurs when broker has a session / after IdP return and exact-matches `client.redirectUrls` — app cannot patch registration for client `grok_05dbc0669ade449c9494894758e3cf0a`.



### Repro

1. Publish app with Better Auth + Grok broker (`genericOAuth` → `auth.grok.me`).  
2. Open `https://arrow-meadow-birch-civic.grok.me/login`.  
3. Continue with Google or X.

### Observed authorize URL (user paste)

```
https://auth.grok.me/api/auth/oauth2/authorize
  ?response_type=code
  &client_id=grok_05dbc0669ade449c9494894758e3cf0a
  &state=…
  &scope=openid+profile+email
  &redirect_uri=https%3A%2F%2Farrow-meadow-birch-civic.grok.me%2Fapi%2Fauth%2Foauth2%2Fcallback%2Ftwitter
```

### Error

```json
{"message":"Invalid redirect URI"}
```

This is the **broker OIDC** exact-match check (`client.redirectUrls.find(url => url === query.redirect_uri)`). It fires when a broker session exists / after IdP return — not a relative-URI bug (redirect_uri is absolute).

### Correct app-generated authorize (current API)

```
https://auth.grok.me/api/auth/oauth2/authorize
  ?idp=twitter
  &prompt=login
  &response_type=code
  &client_id=grok_05dbc0669ade449c9494894758e3cf0a
  &redirect_uri=https://arrow-meadow-birch-civic.grok.me/api/auth/oauth2/callback/twitter
  …
```

App always uses path **`/api/auth/oauth2/callback/{google|twitter}`** (Better Auth `genericOAuth`).

### Platform fix required

When creating the per-app `GROK_AUTH_CLIENT_ID` for publish, register **exact** redirect URIs (comma-separated `redirectUrls` / OIDC `redirect_uris`):

```
https://{slug}.grok.me/api/auth/oauth2/callback/google
https://{slug}.grok.me/api/auth/oauth2/callback/twitter
```

Example for this app:

```
https://arrow-meadow-birch-civic.grok.me/api/auth/oauth2/callback/google
https://arrow-meadow-birch-civic.grok.me/api/auth/oauth2/callback/twitter
```

**Do not** store only a wildcard string as a literal if the broker uses exact `===` match (stock better-auth OIDC). Expand wildcards at validation time **or** materialize concrete URIs at deploy.

Also ensure authorize flows always preserve `idp=google|twitter` (broker headless upstream). App sends `authorizationUrlParams.idp`; user paste without `idp` may be an intermediate hop or older build.

### Health diagnostic (app)

`GET /api/v1/health/auth` includes:

```json
"expectedBrokerRedirectUris": [
  "https://arrow-meadow-birch-civic.grok.me/api/auth/oauth2/callback/google",
  "https://arrow-meadow-birch-civic.grok.me/api/auth/oauth2/callback/twitter"
]
```

---

## Bug A — Missing DATABASE_URL (earlier)

Health previously showed auth client present, all `databaseEnv.*: false`, `publishLikelyBroken: true`.

**Expected:** inject `DATABASE_URL` (Neon) with auth client + `BETTER_AUTH_SECRET` as one atomic deploy environment.

**Temporary agent mitigation:** `scripts/ensure-publish-db.mjs` claimable Neon bootstrap — **not** the product design; **do not** ask users to claim into personal Vercel/Neon.

---

## Product contract

Provisioning of deployment environment (public URL, auth client + **registered redirect URIs**, session secret, durable DB) must be **transparent to the app builder**. Success only when:

```json
{
  "ok": true,
  "mode": "deployed_client",
  "database": "neon",
  "publishLikelyBroken": false
}
```

and browser OAuth completes without `Invalid redirect URI`.

---

## One-line triage

`*.grok.me` publish injects `GROK_AUTH_*` but does not register exact app callback URIs on the broker client (and may omit `DATABASE_URL`); Better Auth genericOAuth uses `/api/auth/oauth2/callback/{google,twitter}` — exact match required or sign-in returns `Invalid redirect URI`.
