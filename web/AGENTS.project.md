This project is the **multi-tenant** portfolio platform:

https://github.com/ivelin/investment-portfolio-analysis

Branch: **`main`** (default; active development)

## Scope

- All product code is under `web/`.
- There is no single-user Python CLI/MCP stack.
- UI, REST, and MCP share `src/lib/portfolio/service.server.ts`.
- Auth product path: Better Auth **Google + X** social only (see `docs/AUTH.md`).

## Rules

- Do not re-scaffold a parallel app at repo root.
- Never commit `src/lib/db-bootstrap.secret.ts` or connection strings.
- Run `npm run ci` (or `make ci` from repo root) before push.
- Multi-tenant isolation and fail-closed auth are non-negotiable.
- Do not reintroduce Grok broker as the Vercel production auth path.
