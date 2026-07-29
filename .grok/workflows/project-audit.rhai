// Grok Build workflow recipe: project-audit (rhai)
//
// INTENT: DRY / MECE cleanup + security + retail compliance audit.
//
// WHERE THIS RUNS
// - Local Grok Build CLI (if your machine supports .rhai workflows): invoke this file.
// - Grok web app-builder sandbox (this PR's CI / `python scripts/project_audit.py`):
//   .rhai execution is NOT available — use the Python/Node audit scripts instead.
//
// STEPS (agent or human)
// 1. Run automated audit:
//      python scripts/project_audit.py
//    (Hosted TanStack app workspace: npm run audit)
// 2. Fix all [BLOCK] findings before merge.
// 3. Review [WARN] for DRY/MECE cleanups (duplicate logic, jargon in UI docs).
// 4. Re-run pytest + ruff (or npm run ci on hosted app).
// 5. Confirm no secrets/PII/live balances in git.
// 6. Confirm product copy: self-management only, not investment advice.
//
// MECE CHECKLIST
// - Isolation: tenant_id on every data path; OAuth session bind
// - Secrets: no tokens, keys, statements in repo
// - OAuth: skip | refresh | needs_reauth matrix single-sourced
// - Compliance: Terms/Privacy/intended-use; not RIA tooling
// - UX: product UI is not technical documentation
// - Tests: isolation + MECE + bind + legal pack stay green
//
// This file is documentation-as-workflow for agents; the executable source of
// truth in THIS repo is scripts/project_audit.py.

fn main() {
    // Placeholder — local Grok Build may interpret workflow files differently.
    // Prefer: `python scripts/project_audit.py`
    print("Run: python scripts/project_audit.py");
}
