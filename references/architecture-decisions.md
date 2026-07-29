# Architecture decisions

## Product shape (2026-07)

- **Decision:** Multi-tenant hosted app only (`web/`).
- **Rationale:** Single deployable for UI, REST, and MCP; Neon for durable
  tenant data; no single-user SQLite/CLI skill in this repository.
- **Rule:** Domain logic in `web/src/lib/portfolio/service.server.ts`; thin
  adapters for UI server functions, REST routes, and `/api/v1/mcp`.

## Database

- **Deploy:** Neon Postgres via `DATABASE_URL` (Vercel).
- **Local dev:** PGLite when `DATABASE_URL` is unset.
- **Serverless without DB:** fail closed (no PGLite on Vercel).

## Auth

- Better Auth self-hosted at `/api/auth/*`.
- Federated Google/X via platform auth broker.
- API/MCP: session cookie or tenant API key (`pa_…`).

## Broker connectivity

- Per-tenant OAuth; tokens sealed in `connector_secrets`.
- Never use a shared operator MCP session as a multi-tenant data feed.

## Analytics engines

- Capital efficiency / TWRR / fund-as-symbol designs under `docs/` are **product
  targets** on tenant data, not a separate local stack.
