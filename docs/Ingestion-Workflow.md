# Portfolio Data Ingestion Workflow

**Canonical Location for Documentation**: This file + [README.md](../README.md#portfolio-data-sources-canonical-location) + [SKILL.md](../SKILL.md)

## Philosophy (Hard Rule)

This portfolio analysis system **only** operates on real, verified, ground-truth data exported directly from Schwab.

- Simulated, interpolated, backfilled, or fabricated daily position values are **never** used for Capital Efficiency / TWRR calculations.
- All analysis features require sufficient real data before producing results.

### Ground Truth File Protection (Permanent Hard Rule)

- The directory `~/.investment-portfolio-analysis/schwab-exports/` (and any user-designated ground truth export directory) contains the **original, immutable Schwab export files**.
- **The agent must never delete, move, rename, or modify any files in the ground truth directory.**
- These files are the user's canonical source of truth. Any derived data (database records, caches, processed files, etc.) may be cleaned or regenerated, but the raw export files themselves are sacred and must remain untouched forever.

## Recommended Canonical Storage

See [README.md#portfolio-data-sources-canonical-location](../README.md#portfolio-data-sources-canonical-location) for the recommended folder structure.

## Files You Must Ingest

For a complete view of your current active positions, you need to ingest (at minimum):

| File Type                              | Ingestion Command                              | Why It Matters                                      | Minimum for Basic Use      |
|----------------------------------------|------------------------------------------------|-----------------------------------------------------|----------------------------|
| **Positions** (dedicated CSVs)        | `portfolio ingest-positions`                   | High-trust daily/periodic snapshots for TWRR       | At least recent dates     |
| **AccountStatement CSVs** (Equities section) | `python tools/ingest_account_statement_equities.py` | Monthly end-of-period position anchors (first-class ground truth) | Strongly recommended for verification |
| **Realized Gain/Loss** (Lot Details)  | (via `ingest_all_schwab_exports.py` or future CLI) | Historical performance per symbol + lots           | Strongly recommended      |
| **Transactions / Activity**           | (via `ingest_all_schwab_exports.py` or future CLI) | Full trade events, fees, corporate actions         | Strongly recommended      |
| **Brokerage Statement / AccountStatement data** | Direct structured CSV/XML/JSON exports → `gt_*` tables (deterministic) | High-fidelity periodic anchors and transactions | Primary / only supported path |

## Current Ingestion Commands (as of May 2026)

```bash
# High-trust daily/periodic snapshots
portfolio ingest-positions \
    --positions /path/to/Schwab_Positions_2026-05-27.csv \
    --as-of 2026-05-27

# Monthly Account Statements (new high-value source of position anchors)
python tools/ingest_account_statement_equities.py
```

The two master scripts (`ingest_all_schwab_exports.py` and `ingest_account_statement_equities.py`) are the recommended way to bulk-ingest when new exports arrive.

## Optimized Ingestion Strategy (Leverage DB First)

All ingestion functions now follow this principle:

1. **Check the local database first** for existing data (latest dates per table/symbol).
2. **Skip expensive file parsing** when the data in the file is older than what we already have (or when we already have that exact `as_of_date` for Positions).

## Master Ingestion Scripts

### Standard Exports
For Positions CSVs, Realized Gains, and Transactions, use:

```bash
python tools/ingest_all_schwab_exports.py
```

### Monthly Account Statements (New)
AccountStatement CSVs contain valuable end-of-period Equities positions. Ingest them with:

```bash
python tools/ingest_account_statement_equities.py
```

These are treated as **first-class ground truth anchors** and are inserted into `gt_brokerage_statement_positions` (the highest-priority source for TWRR quantity reconstruction).

**Date handling**:
- `as_of_date` is derived from the filename.
- The header "through" date is parsed as a cross-check.
- Inconsistencies are recorded as red flags in the `notes` column.

This is now part of the **recommended repeatable workflow** when new monthly statements become available.

**What gets updated:**
- Direct structured exports (AccountStatement CSVs, Positions CSVs, Transactions XML/CSV, Realized Gains) → `gt_brokerage_statement_positions` and sibling gt_* tables (primary path)
- (Retired) Old PDF/Grok route no longer used; historical note in INGESTION_AND_RECONCILIATION_FRAMEWORK.md
- Positions CSVs → `gt_daily_positions` / `daily_position_values`
- Realized Gain/Loss CSVs → `gt_realized_gains`
- Transactions CSVs/XMLs → `gt_transactions`

Both scripts are idempotent and safe to re-run.

**This document is the canonical reference for the ingestion workflow.** It should be updated whenever new ingestion commands or verification rules are added.
