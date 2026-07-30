# CI/CD: GitHub → Vercel preview + Neon branch

Yes — **preview deploys per PR with a matching Neon branch** belong in the
default multi-tenant loop:

| Gate | Role |
|------|------|
| **CI** (`web` workflow) | typecheck + suites + coverage ≥80% |
| **Vercel deploy** (`vercel-deploy` job) | build/deploy + health (`database: neon`) |
| **Required checks on `main`** | both must pass before merge |

## Architecture

```text
git push / PR update
  ├─ GitHub Actions: CI (tests + coverage)
  └─ GitHub Actions: Vercel Deploy
         ├─ vercel pull / build / deploy --prebuilt
         ├─ Neon Marketplace injects DATABASE_URL
         │    (preview branch ≈ preview/<git-branch> when Preview Branching on)
         └─ GET /api/v1/health/auth must be 200
```

Native Vercel↔GitHub “Vercel” check appears **after** the Vercel GitHub App can
see this repository (see below). Until then, the **`vercel-deploy`** Actions job
is the required deploy check.

## One-time setup (human + agent)

### 1. GitHub secrets

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Value |
|--------|--------|
| `VERCEL_TOKEN` | Vercel account token (Settings → Tokens) |
| `VERCEL_ORG_ID` | `team_vhRLfXjbtB0CgVM29W6ErXus` (from `.vercel/project.json` `orgId`) |
| `VERCEL_PROJECT_ID` | `prj_8XrN8JPmq2fyp4mP3IxA42DP4hWN` |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | **Optional.** Vercel → Project → Deployment Protection → Protection Bypass for Automation. Without it, health may get HTTP 302 and the job still passes (deploy already succeeded). |

### 2. Grant Vercel GitHub App access to this repo

Required for **native** PR preview comments and the official “Vercel” check:

1. Open [github.com/apps/vercel](https://github.com/apps/vercel) → **Configure**
2. Under **Repository access**, include `ivelin/investment-portfolio-analysis`
3. In [Vercel project → Settings → Git](https://vercel.com/ivelins-projects-9f9b7132/investment-portfolio-analysis/settings/git):
   **Connect** `ivelin/investment-portfolio-analysis`
4. Confirm **Root Directory** = `web`

CLI attempt without App access fails with “Failed to connect … repository”.

### 3. Neon Preview Branching (Marketplace store)

Already have store **`investment-portfolio-analysis`** connected to the Vercel
project for **production + preview**.

Enable automated branching (dashboard):

1. Vercel → **Storage** → Neon store `investment-portfolio-analysis` → **Projects**
2. Edit connection → enable **Preview** deployments
3. Enable **Resource must be active before deployment**
4. Save

Effect: each Vercel preview gets Neon branch `preview/<git-branch>` and a
deployment-scoped `DATABASE_URL` (not visible as a static preview env var).

Build already runs migrations: `npm run build` → `vite build && npm run db:migrate`.

### 4. Auth env (Google + X social — no email/password)

See [AUTH.md](./AUTH.md).

| Env | Preview | Production |
|-----|---------|------------|
| `DATABASE_URL` | Neon integration / branch inject | Neon production |
| `BETTER_AUTH_SECRET` | set | set |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | set | set |
| `TWITTER_CLIENT_ID` / `TWITTER_CLIENT_SECRET` | set | set |
| `BETTER_AUTH_URL` | **omit** (uses `VERCEL_URL`) | optional fixed prod URL |
| `VITE_AUTH_ENABLED` | `true` | `true` |
| `GROK_AUTH_*` | **do not use on Vercel** | n/a |

OAuth app callbacks:

```text
https://<host>/api/auth/callback/google
https://<host>/api/auth/callback/twitter
```

### 5. Required status checks (branch protection)

On `main` (and optionally PR merge):

- `web (typecheck + suite)` — from `.github/workflows/ci.yml`
- `vercel-deploy` — from `.github/workflows/vercel-preview.yml`

```bash
# Example (needs admin); adjust contexts if GitHub renames jobs
gh api -X PUT repos/ivelin/investment-portfolio-analysis/branches/main/protection \
  -f required_status_checks='{"strict":true,"contexts":["web (typecheck + suite)","vercel-deploy"]}' \
  -F enforce_admins=true \
  -F required_pull_request_reviews=null \
  -F restrictions=null
```

After Vercel Git is connected, you can also require the native **Vercel** check
(deployment success). Prefer keeping **`vercel-deploy`** until that check is
stable on every PR.

## Local

```bash
make ci                 # tests + coverage
# Deploy preview manually from web/:
cd web && vercel --yes
```

## Why this fits multi-tenant

- **Isolation:** Neon branch per git branch → schema/data experiments don’t
  touch prod.
- **Auth realism:** real HTTPS origin + Better Auth on `*.vercel.app`.
- **Fail closed:** health requires `database: neon` when `DATABASE_URL` is set.
- **No Grok App dependency** for the shipping loop (handover can come later).
