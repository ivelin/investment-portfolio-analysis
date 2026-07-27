# Test Fixture Exports (Ground Truth Documents)

This directory is for **optional local** raw Schwab/TDA export files used by the
offline import harness. **Real personal exports must never be committed.**

## Git policy

- `*.csv`, `*.xml`, and `*.pdf` are gitignored at the repo root.
- Only this `README.md` is tracked under this directory.
- Do not force-add personal Positions / Transactions / GainLoss exports.

## Synthetic / redacted samples

For CI and public clones, prefer the synthetic JSON extractions under:

- `tests/fixtures/extractions/brokerage_statements/`
- `tests/fixtures/extractions/tax_documents/`

Those files use placeholder account `999-000001` and tiny synthetic holdings.
They are **not** real balances or tax data.

## Local private workflow

Place your real exports under `~/.investment-portfolio-analysis/schwab-exports/` (outside
the git tree) and point tools at that path. Never copy unredacted personal
exports into this repository when preparing a public push.
