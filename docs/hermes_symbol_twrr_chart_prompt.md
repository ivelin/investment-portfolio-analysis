# Hermes Prompt: Correctly Generate Per-Symbol TWRR + OHLC + Position Size Chart

You are an agent with access to the portfolio-analysis project at the user's workspace root (the directory that contains `pyproject.toml` and `src/portfolio_analysis/`).

The user wants a clean, trustworthy 3-panel chart for a specific symbol (example: AAPL or any held ticker):

- Top panel: cumulative TWRR (time-weighted return) from the canonical daily_twrr table.
- Middle panel: price (OHLC or close line) from the local price cache.
- Bottom panel: position size as a **clean step function** (date → shares held) with **no gaps, no anomalous spikes, no long zero periods**.

**Critical constraints (from the project history and fixes):**
- Never query `daily_position_values` directly for the position series in charts or reports (it can contain bad spikes when "Journal" internal adjustment transactions were treated as normal trades).
- Never rely only on sparse `gt_daily_positions` snapshots for the full series.
- The single source of truth for a continuous daily position quantity series is the anchored reconstruction: latest good snapshot from `gt_daily_positions` as the starting qty, *only* apply subsequent real Buy/Sell transactions (strictly after the anchor date), **completely ignore "Journal" entries** (they are internal adjustments/transfers with no net economic effect on plotted position size).
- The reconstruction must produce a dense daily series (reindex + ffill) for a perfect step plot.
- All TWRR numbers must come from the reconciled `daily_twrr` (populated via subperiod HPR + gapfill with boundary validation).
- Pre-period holdings must be respected (do not start from zero for a YTD-style window if there were prior tx or an earlier anchor).
- Always reconcile first when numbers look suspicious or after new exports.

**Exact pre-requisite steps (execute in order; do not skip):**

1. Make sure you are in the portfolio-analysis directory (workspace root).
   cd /path/to/portfolio-analysis

2. Ensure the latest raw Schwab exports are present under the instance home (`$PORTFOLIO_ANALYSIS_HOME/exports/schwab/` or legacy `schwab-exports/`). If new files were added, run the ingestors:
   python tools/ingest_all_schwab_exports.py
   python tools/ingest_account_statement_equities.py

3. **Reconcile positions and TWRR for the symbol(s) of interest** (this snaps GT anchors from gt_daily_positions / statements, runs the correct reconstruction, populates daily_twrr, and ensures clean derived values). Use --loop for the self-healing behavior:
   python tools/build_reconciled_daily_positions.py \
       --symbols AAPL \
       --start-date 2026-05-01 \
       --end-date 2026-05-28 \
       --loop --max-iterations 3

   (Adjust symbols and dates as needed. This is mandatory for correct anchors and to avoid garbage in the chart.)

   After this, you can optionally verify the position series directly:
   python -m portfolio_analysis.cli daily-positions --symbol AAPL --start-date 2026-05-20 --end-date 2026-05-28

   Look for:
   - On GT snapshot dates, quantity matches `gt_daily_positions` for that symbol
   - On Journal-only days, quantity is carried (no artificial inflation)
   - Clean step (flat where no real trades, jumps only on real Buy/Sell), no long zeros while held

4. Generate the chart using the dedicated consolidated CLI subcommand (this is the supported way; it calls the generator that sources the bottom panel exclusively from the reliable recon):
   python -m portfolio_analysis.cli chart twrr-ohlc-position \
       --symbol AAPL \
       --start-date 2026-05-01 \
       --end-date 2026-05-28 \
       --output /tmp/symbol_twrr_ohlc_position.png

   (If the `portfolio` entrypoint is installed and in PATH you can use `portfolio chart ...` directly.)

   - `--start-date` / `--end-date` optional but recommended for reproducibility.
   - Output defaults to the reports dir (`$PORTFOLIO_ANALYSIS_HOME/reports/` or `$PORTFOLIO_ANALYSIS_REPORTS_DIR`) with a timestamped name if not provided.

**Post-generation verification (always "check your work" before presenting):**
- Confirm the command succeeded (exit 0) and printed "Chart saved to: …png".
- The PNG file exists and has reasonable size (>10kB).
- Re-run the daily-positions command and confirm quantities match GT anchors (no Journal spikes).
- The bottom panel of the PNG must look like a step function (horizontal lines between event dates, vertical jumps only on real trades, anchored to the GT position sizes on snapshot dates).
- If anything looks off, re-run the reconciliation step (step 3) and regenerate.

**Implementation notes for you (the agent):**
- The underlying function is `portfolio_analysis.charts.generate_twrr_ohlc_position_chart`.
- It obtains the position series via `portfolio_analysis.reporting.get_daily_position_series_for_symbol` → `reconstruct_daily_position_quantities` (the MECE canonical implementation in daily_positions.py).
- TWRR panel pulls from `daily_twrr` (after the recon tool populates it via subperiods + gapfill).
- Prices come from the local `market_price_bars` cache (populated on demand by market_data helpers).
- All of this is exposed via the `portfolio` CLI (entry point in src/portfolio_analysis/cli.py). Prefer the CLI for hermes workflows.
- The (deprecated) `daily_position_values` table may still contain old bad rows for dates outside your recon window — the chart code deliberately does **not** use it for the series.

**Example full hermes command sequence (copy-paste; substitute symbol/dates):**
```bash
cd /path/to/portfolio-analysis
python tools/build_reconciled_daily_positions.py --symbols AAPL --start-date 2026-05-01 --end-date 2026-05-28 --loop --max-iterations 2
python -m portfolio_analysis.cli daily-positions --symbol AAPL --start-date 2026-05-20 --end-date 2026-05-28
python -m portfolio_analysis.cli chart twrr-ohlc-position --symbol AAPL --start-date 2026-05-01 --end-date 2026-05-28 --output /tmp/symbol_demo.png
ls -l /tmp/symbol_demo.png
```

If the user asks for a different symbol or date range, substitute accordingly and always re-reconcile first.

**X-axis formatting requirement:**
- The X-axis must use clean monthly major ticks (`%b %Y`) with minor weekly ticks.
- No overlapping date labels.
- Rotation should be ~30° with readable font size.
- This is part of the visual regression expectation for all symbol charts.
