# Portfolio Analysis — Ingestion & Reconciliation Framework

**Status**: Active (as of 2026-05)
**Philosophy**: High-fidelity, auditable ground truth exclusively from direct Schwab structured exports (CSV, XML, JSON). All position, transaction, and realized-gains data lands in immutable `gt_*` tables via deterministic parsers. Daily position reconstruction is conservative (hard anchors + validated transaction dates only; minimal interpolation). TWRR and Capital Efficiency metrics derive solely from this pristine layer. PDF extraction (local or SOTA VQA) is not used.

---

## 1. Export Types & Ingestion Strategy

All data comes from direct Schwab/TDA structured exports (no PDF parsing or VQA extraction).

| Type | Example Files | Primary Table | Ingestion Method | Notes |
|------|---------------|---------------|------------------|-------|
| **Monthly AccountStatement CSVs** | `YYYY-MM-DD-AccountStatement.csv` | `gt_brokerage_statement_positions` (high-quality periodic anchors) | Deterministic Python (Equities section) | `tools/ingest_account_statement_equities.py` — first-class high-fidelity snapshots |
| Positions CSV | `*_Positions_*.csv` | `gt_daily_positions` | Deterministic parser | `tools/ingest_positions_csv.py` + `02_positions_csv.md` |
| Realized Gain/Loss CSV | `*_GainLoss_Realized_*.csv` | `gt_realized_gains` | Deterministic parser | `tools/ingest_*.py` helpers + `03_realized_gains_csv.md` |
| Transactions CSV | `*_Transactions_*.csv` | `gt_transactions` | Deterministic helper | `04_transactions_csv.md` |
| Transactions XML | `*_Transactions_*.xml` | `gt_transactions` (primary) | Direct XML parse (lxml/ElementTree) | `05_transactions_xml.md`; also feeds derived `transactions` for compatibility |
| Other direct JSON/CSV exports | Various Schwab structured files | Appropriate `gt_*` table | Direct structured ingest | Future-proof for any new Schwab export formats |

**Note on AccountStatement CSVs**: These provide excellent periodic position anchors directly into `gt_brokerage_statement_positions`. They are the preferred modern source for statement-like fidelity without any extraction step. See `docs/Ingestion-Workflow.md` for details.

**Historical note**: PDF extraction (both local pdfplumber and SOTA VQA multimodal models) was attempted during early development for TDA/Schwab brokerage statements but was abandoned. Direct structured CSV, XML, and JSON exports from Schwab provide equivalent or superior ground-truth position, transaction, and realized-gains data with full auditability and no extraction ambiguity. Only the one-time historical SOTA prompt remains archived in `docs/archive/extraction_prompts_sota_vqa/`. All active paths use direct structured exports only.

---

## 2. Regression Test Framework

Location: `tests/test_ingestion_integrity.py` (expanded)

Core principles:
- Every major ingest type has dedicated regression tests.
- Tests must pass against the curated fixture set before any production ingestion.
- Tests enforce **no duplicates**, **quantity reconciliation** against GT anchors, and **coverage** of known statement dates.

### Key Eval Categories (to be expanded)

1. **Duplicate Prevention**
   - No duplicate economic events after ingesting any file type.
   - `gt_transactions` and `transactions` must not have exact (symbol, date, qty, amount, description) duplicates.

2. **GT Anchor Fidelity**
   - After ingesting a known statement JSON, the exact quantity for key symbols (e.g., synthetic fixture AAA on a statement `as_of_date`) must be present in `gt_brokerage_statement_positions`.

3. **Reconciliation Consistency**
   - For every symbol with a GT statement anchor, `_get_quantity_as_of(anchor_date, ...)` must return a value within tolerance of the anchor quantity.

4. **Cross-Source Consistency**
   - Sum of deltas from `gt_transactions` between two GT statement dates should be consistent with the change in position quantity.

5. **Garbage Collection**
   - No orphaned rows in derived tables after a clean full ingest.
   - Old backfill or legacy data must be absent.

---

## 3. Full Clean Cycle Runbook (Recommended)

1. **Preparation**
   - Delete `~/.portfolio-analysis/portfolio.db` (or use a fresh test DB).
   - Ensure all raw direct structured exports (CSV/XML/JSON) are in `~/.portfolio-analysis/schwab-exports/`.

2. **Ingestion (direct structured only)**
   - Run the master ingestion scripts: `tools/ingest_all_schwab_exports.py`, `tools/ingest_account_statement_equities.py`, `tools/ingest_positions_csv.py` (current canonical implementations).
   - These populate `gt_*` tables directly from the exports with full provenance.

3. **Reconciliation**
   - Run `recalculate_position_sizes()`.
   - Run the full set of integrity tests + evals in `tests/test_ingestion_integrity.py`.

4. **Garbage Collection**
   - Remove any data that landed in legacy tables (`daily_position_values`, legacy `realized_gains`, etc.) if GT versions exist.
   - Clean any remaining duplicate rows.
   - Vacuum / compact if needed.

5. **Verification**
   - Run `portfolio twrr --symbols AAPL --detailed` (and full portfolio).
   - Confirm no "INCONSISTENCY DETECTED" warnings on periods that now have proper anchors.
   - Compare against known statement dates and position quantities from the raw exports.

---

## 4. Current Gaps (as of last audit)

- 2023-era quantity reconciliation for certain symbols (e.g. AAPL) required targeted GT anchor backfills from available structured exports.
- Gaps are now addressed via exhaustive re-ingestion of all direct Schwab CSV/XML/JSON exports + the self-healing daily reconstruction loop.
- Ongoing: Expand coverage of AccountStatement CSVs and cross-validate against realized gains + price data.

---

## 5. Daily Position Reconstruction Engine (New – 2026-05)

To support high-quality TWRR and other analytics, we now maintain a **granular daily (or near-daily) positions table** as the "golden source of truth".

### Philosophy
- **Minimize interpolation aggressively** — Rows are only created on dates with real source data (GT statement positions, bulk Positions CSVs, or transaction dates).
- **Use real prices** — Historical OHLC data (via the `market_data` layer) is attached for market value on derived rows whenever possible.
- **Leverage realized gains** — `gt_realized_gains` is used both for reconstruction validation and as a cross-check on close dates.
- **"Pristine" standard** — A symbol’s daily data is considered pristine when:
  - ≥ 90% of rows have `data_quality ≥ 85` (direct from statements or positions CSVs + real price)
  - ≤ 5% low-quality derived rows
  - Strong consistency with realized gains on close dates
  - No phantom positive positions after a known full close (unless a later GT anchor re-opens the position)
  - TWRR reports generated from the table show zero (or near-zero) inconsistency warnings

### Key Components
- `src/portfolio_analysis/daily_positions.py`
  - `collect_hard_anchors()` / reconstruction helpers
  - `reconstruct_daily_positions_for_symbol()` — conservative (hard anchors + validated tx dates + realized gains cross-checks only)
  - `evaluate_reconstruction()` — returns `is_pristine` flag + detailed metrics (coverage, quality tiers)
  - `force_snap_relevant_anchors()` / `force_snap_to_gt_anchors()` — targeted correction
- `tools/build_reconciled_daily_positions.py`
  - Main orchestration script with self-healing loop
  - Continues reconstruction + targeted correction + garbage collection until all symbols are pristine (or max iterations)
  - Writes a final fixed-name `Daily_Positions_Pristine_Report.txt` artifact

### Self-Healing Loop Pattern
The script repeatedly runs:
1. Conservative reconstruction (anchors + transactions + real prices + realized gains validation)
2. Headless evaluation (daily metrics + TWRR inconsistency signals)
3. Targeted correction (force-snap relevant GT anchors near problematic dates)
4. Garbage collection (remove low-quality derived rows for symbols that are now clean)

It only exits when `is_pristine == True` for all symbols (or safety limit reached).

### Regression Tests
New daily-position-specific evals were added in `tests/test_ingestion_integrity.py`:
- No phantom positions after last known close
- High real-source coverage requirement (≥70% high quality in fixtures)
- Realized gains consistency on close dates
- Anchor fidelity (reconstructed quantities match GT statements on anchor dates)

These tests must pass before considering any production daily positions data "pristine".

---

**Next Action**: Ensure all direct structured Schwab exports (AccountStatement CSVs, Positions CSVs, Transactions CSVs/XML, Realized Gains CSVs, etc.) are in `~/.portfolio-analysis/schwab-exports/`, then run the self-healing reconciliation:

```bash
python tools/build_reconciled_daily_positions.py \
    --sacred-dir ~/.portfolio-analysis/schwab-exports \
    --loop \
    --max-iterations 8 \
    --verify-aapl
```

Monitor the loop until it reports "PRISTINE" (zero daily + TWRR inconsistencies) and review the generated report at:
`/tmp/portfolio-analysis-reports/Daily_Positions_Pristine_Report.txt`

This document is the single source of truth for the direct-structured-export ingestion policy, GT tables, conservative daily reconstruction, and pristine verification criteria. The active extraction guidance for CSV/XML lives in `docs/extraction_prompts/02_*` through `06_*`.

### Multi-symbol reconciliation and gap closing (TSLA and portfolio)
- Overlapping export files (e.g. multiple Realized_Gains_Details and Transactions CSVs for different export runs) can cause duplicate rows in gt_realized_gains / gt_transactions when using simple OR IGNORE. This leads to phantom qty bloat, extreme sub HPRs, and garbage TWRR % (e.g. 100k%+ or -1e9%).
- Always dedup GT tx/realized on business keys (symbol + dates + qty + price/amount/gain) after bulk ingest from multiple files, then re-run targeted `build_reconciled_daily_positions.py --symbols TSLA,... --loop`.
- Re-ingest AccountStatements (and full via ingest_all) after parser improvements (header-aware Mark Value + self-heal) to refresh bad MV anchors for all symbols.
- Use bar closes consistently for sub HPR p_start/p_end (via _get_prices) so gapfill residuals stay small and boundary products match.
- Some high-frequency symbols (TSLA etc) will have dozens of subs and legitimately large window TWRR % due to scaling in/out around moves; reports now surface the numbers (no N/A suppression) after recon.
- Run `twrr --symbols TSLA NVDA ...` (or --all) post-recon to verify; auto price ensure + daily_twrr path.
- Gaps closed for key holdings (TSLA had 147 daily_twrr rows + recon after dedup/clean). Some thin symbols may retain partial coverage or warnings; loop + snaps improve them.
