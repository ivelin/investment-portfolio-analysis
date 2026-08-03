# Broker resilience (read-only analysis)

Financial data must stay grounded when OAuth tokens expire or broker APIs change shape.

## Hard rules

1. **Read-only only** — connectors never place orders (see [BROKER_READ_ONLY.md](./BROKER_READ_ONLY.md)).
2. **Never invent numbers** — missing NLV is not zero; incomplete totals are flagged.
3. **Last-known-good** — failed sync keeps accounts, positions, and sealed tokens; connector becomes `needs_reauth` or `error`.
4. **Contract validation** — Schwab payloads are parsed with version-aware helpers; unparseable shapes do not overwrite books.
5. **DB isolation** — preview/tests use isolated PGLite only; never publish Neon ([test-db-isolation](../scripts/test-db-isolation.mjs)).

## Status model

| Status | Meaning | UX |
| --- | --- | --- |
| `connected` | Last sync ok | Sync / Disconnect |
| `error` | Transient / unknown / contract | Retry sync; connection kept |
| `needs_reauth` | Tokens unusable | Reconnect; last holdings shown |

## Tests

- `broker-resilience` — pure math, freshness, contract parse, reauth keeps LKG
- `broker-sync` — 401 → `needs_reauth`, tenant isolation
- `db-isolation` — preview never resolves publish bootstrap URL
