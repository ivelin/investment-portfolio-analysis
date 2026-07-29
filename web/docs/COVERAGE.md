# Coverage policy (multi-tenant web)

## Goal

Maintain **≥ 80% line coverage** on the **critical include set** (domain + API/MCP
handlers + auth health/runtime). Measured with `c8 --all` so unhit files count
as zero — no inflated “only loaded modules” reports.

## Command

```bash
cd web
npm run test:coverage   # unit+api+mcp + c8 gate (fails under 80% lines)
npm run test:e2e        # browser home+login (or documented skip)
npm run ci              # typecheck + test:coverage + test:e2e
```

From repo root: `make ci` (includes coverage gate). Pre-push runs `make ci`.

Thresholds (`.c8rc.json`): **lines ≥ 80**, statements ≥ 80, branches ≥ 55, functions ≥ 60.
`c8 --all` counts unhit files in the include set as zero coverage.

## Include set (MECE)

| Included | Why |
|----------|-----|
| `src/lib/portfolio/**` | Domain SSOT for UI / REST / MCP |
| `src/routes/api/**` | Shipped HTTP handlers |
| `src/lib/security/**` | Redaction / ids / oauth bind guards |
| `src/lib/compliance/**` (server + pure) | Legal / intended-use |
| `src/lib/db.ts`, `db-url.ts`, `runtime-env.ts` | Data plane |
| `src/lib/auth/auth-runtime-status.ts` | Health endpoint truth |

## Explicitly out of scope (not fluff-chased)

- Generated `routeTree.gen.ts`
- Presentational UI routes (`src/routes/*.tsx`) and Radix chrome
- Better Auth browser client / popup / preview constants
- Server-fn wrappers that only re-export domain (`*-queries.ts`) when handlers already cover the path
- Multiplayer / unused P2P helpers

E2E still proves **home + login** are reachable (or documents environment unavailability under scratch).

## Suites

| Pack | Path | Role |
|------|------|------|
| unit (legacy scripts) | `scripts/test-*.mjs` | Isolation, OAuth, token refresh, MECE |
| **api** | `tests/api/critical-path.mjs` | summary, health, job auth |
| **mcp** | `tests/mcp/critical-path.mjs` | catalog + tools |
| **e2e** | `tests/e2e/entry-smoke.mjs` | browser entry or honest skip |

Override coverage gate only with `SKIP_COVERAGE=1` (not silent).
