# Project audit (rhai checklist)

Keep docs, tests, and contracts **DRY** and **MECE**. Scan for security and retail-compliance liabilities.

## Run (this public repo)

```bash
python scripts/project_audit.py
# or
make audit
```

CI runs the same step on every PR (`Project audit (rhai checklist)`).

## Grok Build `.rhai` workflows

| Environment | Supported? |
|-------------|------------|
| **Local Grok Build CLI** on your machine | If your local Grok Build install supports `.rhai` workflows, use [`.grok/workflows/project-audit.rhai`](../.grok/workflows/project-audit.rhai) as the recipe. |
| **Grok web / app-builder sandbox** (hosted Build chat) | **No** — there is no `grok` CLI and no Rhai runner here. Use `python scripts/project_audit.py` (this repo) or `npm run audit` (hosted TanStack workspace). |

The `.rhai` file is a **portable recipe** for agents/humans. The **executable** source of truth in this repository is `scripts/project_audit.py`.

## Checklist (MECE)

| Area | Check |
|------|--------|
| Isolation | Hosted paths scoped by `tenant_id`; OAuth state binds user+tenant; session bind on callback |
| Secrets | No tokens, balances, PII, or live portfolio dumps in git |
| OAuth | Refresh matrix `skip` / `refresh` / `needs_reauth` single-sourced |
| Compliance | Self-management only; not advice; not professional client services |
| Legal | Versioned Terms+Privacy acceptance (hosted app); docs in this repo |
| UX | Product UI is not technical documentation |
| Tests | Isolation, MECE, OAuth bind, legal pack docs stay green |

## Hosted app (separate workspace)

The multi-tenant TanStack web app in Grok Build also has:

```bash
npm run audit    # scripts/project-audit.mjs
npm run ci
```
