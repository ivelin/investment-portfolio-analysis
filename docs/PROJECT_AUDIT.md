# Project audit (rhai) — multi-tenant platform

Keep docs, tests, and contracts **DRY** and **MECE**. Run on every PR.

## Checklist (blocking intent)

| Area | Check |
|------|--------|
| Isolation | Every hosted data path scoped by `tenant_id`; OAuth state binds user+tenant |
| Secrets | No tokens, balances, PII, or live portfolio dumps in git |
| OAuth | Session bind on callback; refresh matrix skip/refresh/needs_reauth |
| Compliance | Self-management only; not advice; not professional client services |
| Legal | Versioned Terms+Privacy acceptance before private use |
| UX | Product UI is not technical documentation |
| Tests | Isolation, MECE decisions, OAuth bind, legal pack docs stay green |

## Hosted app

The Grok Build workspace runs `npm run audit` / `npm run ci` (includes `scripts/project-audit.mjs`).

## This repo

```bash
uv run pytest tests/ -q
uv run ruff check .
```

CI: `.github/workflows/ci.yml` → `lint-and-test`.
