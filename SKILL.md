---
name: portfolio-analysis
description: "Use when analyzing personal brokerage portfolio performance from Schwab. Primary interface is the `portfolio` CLI (`portfolio report`, `portfolio twrr`, `portfolio ingest-positions`, etc.). Supports automatic discovery + ingestion of real Schwab exports. Focuses on CANSLIM + rigorous Daily TWRR Capital Efficiency using only verified data.

Data Sources:
- The skill has no watched directory inside the git repo. Users pass export paths or use the instance home.
- **Canonical instance home (outside the source repo)**: `~/.portfolio-analysis/` (`PORTFOLIO_ANALYSIS_HOME`). Implemented in `src/portfolio_analysis/paths.py`.
  - Exports (immutable GT): `$PORTFOLIO_ANALYSIS_HOME/exports/{broker}/` (preferred; or `PORTFOLIO_ANALYSIS_EXPORTS_DIR`). Legacy `schwab-exports/` still supported for Schwab-only trees. Never delete/modify agent-side.
  - SQLite: `$PORTFOLIO_ANALYSIS_HOME/portfolio.db` (or `PORTFOLIO_ANALYSIS_DB_PATH`).
  - Reports/charts: `$PORTFOLIO_ANALYSIS_HOME/reports/` (or `PORTFOLIO_ANALYSIS_REPORTS_DIR`).
  - Tokens / skill `.env`: under the same home (see SECURITY.md).
- Never write personal instance data into the git worktree. Synthetic fixtures under `tests/fixtures/` only.
- Only direct, verified exports from Schwab (CSV or official XML) are accepted. No simulated or backfilled daily data is ever used for Capital Efficiency / TWRR calculations.
- Ingestion of real Schwab exports is handled *implicitly*. Analysis commands (`report`, `twrr`, etc.) automatically discover and ingest real data from known locations before running. Manual ingestion is optional for advanced control.

**Recommended repeatable workflow**:
- Run `python tools/ingest_all_schwab_exports.py` when new standard exports (Positions, Realized, Transactions) are added.
- Run `python tools/ingest_account_statement_equities.py` when new monthly AccountStatement CSVs are added. These provide high-quality end-of-period position snapshots that serve as first-class ground truth anchors in `gt_brokerage_statement_positions` for validation and reconciliation of TWRR reconstructions.

See [docs/Ingestion-Workflow.md](docs/Ingestion-Workflow.md) for full details (and [docs/README.md](docs/README.md) for the documentation index)."

## Architectural Direction (2026-05)

As documented in [references/architecture-decisions.md](references/architecture-decisions.md), the `portfolio` CLI is now the primary and preferred interface for tools and workflows in this skill.

**Going forward:**
- New tools and features are added as subcommands under `portfolio` (e.g. `portfolio twrr build`, `portfolio ingest ...`).
- Direct use of scripts in `tools/` is considered legacy/internal.
- All new development should follow the principle that the CLI is the single, discoverable entry point (`portfolio --help`).

Existing `tools/` scripts will continue to work after `uv pip install -e .`, but over time they will be converted into proper CLI subcommands or called internally by the `portfolio` command.
version: 1.1.0
author: Ivelin Ivanov
license: Apache-2.0
metadata:
  hermes:
    tags: [portfolio, schwab, canslim, performance, irr, investing, trades]
    related_skills: [stock-analysis, deep-research, cron, native-mcp]
---

# Portfolio Analysis Skill

## Overview

Dedicated skill and codebase for importing, analyzing, and continuously improving a personal portfolio using data from Charles Schwab Developer API. Focuses on **CANSLIM** methodology and hard performance metrics (IRR, ROI, expectancy, drawdown) with the goal of matching or exceeding top practitioners.

This is the canonical implementation living in https://github.com/ivelin/portfolio-analysis.

## CLI Usage (Primary Interface)

The skill exposes a command-line tool called `portfolio`. All analysis should be performed by invoking this CLI (the skill will call it under the hood when needed).

### Invocation

```bash
portfolio <command> [options]
```

The binary is installed via the package (`portfolio = "portfolio_analysis.cli:main"`).

### Core Commands

| Command                        | Purpose                                      | Key Flags                                      | Notes |
|--------------------------------|----------------------------------------------|------------------------------------------------|-------|
| `portfolio report`             | Generate Weed the Garden style report       | `--period`, `--year`, `--symbol`, `--format`   | Supports ytd, last-N-months, specific year |
| `portfolio twrr`               | Show Capital Efficiency (Daily TWRR) table  | `--all`                                        | Uses real daily position data only. Auto-ingests if possible. |
| `portfolio ingest-positions`   | Ingest real Schwab Positions snapshot       | `--positions PATH --as-of YYYY-MM-DD`          | Primary way to feed daily data for TWRR |
| `portfolio pdf-report`         | Generate professional PDF report            | `--positions PATH --output PATH`               | Uses current Positions CSV |
| `portfolio chart distribution` | Position size distribution chart            | `--positions PATH --output PATH`               | Visualization only |
| `portfolio daily-positions`    | Anchored daily qty series (for charts)      | `--symbol S --start-date D --end-date D`       | Clean step series; ignores Journals; used by twrr-ohlc-position chart |
| `portfolio chart twrr-ohlc-position` | TWRR/OHLC/Position step chart          | `--symbol S [--start-date] [--end-date]`       | Bottom panel from recon (no bad daily_position_values data) |

### Implicit Ingestion Behavior

Analysis commands (`report`, `twrr`, etc.) **automatically** attempt to discover and ingest real Schwab export files from these locations if the local database lacks sufficient data (in priority order):

- `~/.portfolio-analysis/schwab-exports/` (primary ground truth location — never delete files here)
- `~/.hermes/cache/documents/`
- `~/Documents/Schwab-Exports/`
- `~/Documents/Schwab-Exports (or set PORTFOLIO_ANALYSIS_EXPORTS_DIR)/`

## Local CI/CD Process (Mandatory)

All development must go through the local CI/CD pipeline before creating a PR.

### Quick Commands

```bash
make ci              # Run full local CI (lint + tests)
make test            # Run TWRR regression tests
make lint            # Run linters
make format          # Auto-format code
make install-hooks   # Install pre-commit hooks
```

### Pre-commit Hooks

Install once:

```bash
make install-hooks
```

After installation, the following checks run automatically on every `git commit`:

- Trailing whitespace & file formatting
- YAML validation
- Ruff linting + formatting
- **TWRR Regression Tests** (`test_twrr_regression.py`)
- **TWRR Data Quality Validation** (`tools/validate_twrr.py` — will move under the `portfolio` CLI)

### Required Before Every PR

1. Run `make ci` and confirm it passes
2. Ensure all TWRR regression tests pass
3. Update documentation if behavior changes
4. Never bypass pre-commit hooks

Failure to follow this process will result in PR rejection.
## TWRR Daily Time-Weighted Return Workflow (2026-05)

**Core Principle**: Only compute TWRR for symbols that are **relevant** (currently held or have recent anchors). When position size is zero, record **0%** return instead of deleting rows or computing spurious values.

> **Note (2026-05)**: Per the [architecture decision](references/architecture-decisions.md), new TWRR tooling and workflows are being migrated into the `portfolio` CLI. Over time the commands below will be available as `portfolio twrr ...` subcommands.

### Current Recommended Tools

| Tool                          | Purpose                                      | When to use                     |
|-------------------------------|----------------------------------------------|---------------------------------|
| `tools/coverage_report.py`    | Shows price coverage quality for all relevant symbols | Before any major TWRR work     |

| `tools/twrr_holdings_report.py` | Clean report focused only on current holdings | Daily / weekly review          |
| `tools/validate_twrr.py`      | Data quality checks                          | As part of local CI             |

### Recommended Sequence (Current)

```bash
# 1. Check data health
python tools/coverage_report.py --csv

# 2. Rebuild TWRR for all relevant symbols (respects coverage + relevance)
# Use build_reconciled_daily_positions.py for TWRR population (now under portfolio CLI direction)

# 3. Review current holdings
python tools/twrr_holdings_report.py --days 30
```

As the `portfolio twrr` subcommands are implemented, the above will be replaced by cleaner CLI equivalents (e.g. `portfolio twrr build --all`).

### Hard Rules

- Never delete historical `daily_twrr` rows for symbols no longer held.
- Zero-size positions must produce `daily_return = 0.0`.
- The `get_relevant_symbols()` function in `twrr_utils.py` controls what gets newly computed.
- All new TWRR code must go through `make ci` (lint + regression tests).

See `tests/test_twrr_regression.py` for the required regression suite.

## Data Ingestion

See the canonical reference: [docs/Ingestion-Workflow.md](docs/Ingestion-Workflow.md)

Key points for agents:
- All data must come from direct, verified Schwab exports (no fabricated values).
- The two primary ways to bring in new data are:
  - `python tools/ingest_all_schwab_exports.py` (standard exports)
  - `python tools/ingest_account_statement_equities.py` (monthly Account Statements → high-quality position anchors)
- Over time these will be integrated as `portfolio ingest ...` subcommands.
- Analysis commands attempt implicit ingestion when needed.
- Monthly AccountStatement CSVs are now treated as **first-class ground truth** for position verification and TWRR reconciliation.


## Options as Independent Assets

As of the 2026 migration, options are treated as **first-class independent assets**.

- Each option contract has its own symbol (e.g. `TSLA 12/15/2028 400.00 C`).
- Use `portfolio twrr --separate-options` to see equities and options in clearly separated sections.
- The `classify_symbol()` helper in `twrr_utils.py` is the single source of truth for classification.

## YTD TWRR + Broker P/L % Portfolio Table Workflow

**Trigger phrases (use this workflow when user says these or close variants):**
- "run ytd twrr and p/l % for all my positions"
- "show me the twrr table for my portfolio"
- "ytd performance table with top twrr performers at the start of the table"
- "portfolio ytd twrr and p/l report"
- "twrr table for all holdings sorted by ytd"

**Purpose:** Produce a single clean table for *all current equity positions* (from latest gt_daily_positions) combining:
- YTD TWRR % (from daily_twrr fast path or subperiods)
- Broker P/L % and P/L YTD $ (parsed from the "Profits and Losses" section of the latest AccountStatement CSV)

Table columns (example): Symbol | Qty | Mkt Val | YTD TWRR% | Broker P/L % | P/L YTD $ | Mark Val

**Always sort descending by YTD TWRR %** (top performers first). Filter strictly to equities (symbols without spaces or option patterns like "2028").

### Prerequisites
- Fresh data recommended: Run reconciliation if daily_twrr is stale or numbers look extreme/garbage (e.g. millions %):
  ```bash
  python tools/build_reconciled_daily_positions.py \
    --start-date 2026-01-01 \
    --loop --max-iterations 2
  ```
  (This rebuilds daily positions, pops daily_twrr with canonical logic + gapfill + validation.)
- Latest AccountStatement CSV present under `$PORTFOLIO_ANALYSIS_HOME/exports/schwab/` (or legacy `schwab-exports/`) in any account subfolder’s `AccountStatements/` path. The most recent matching `*AccountStatement*.csv` is used for P/L %.

### Exact Workflow Steps (executable by agent)

1. **Discover latest holdings (equities only)**
   - Connect to DB (`~/.portfolio-analysis/portfolio.db` or PORTFOLIO_ANALYSIS_DB_PATH).
   - Find latest `as_of_date` in `gt_daily_positions`.
   - SELECT symbols with quantity > 0 on that date.
   - Filter: symbol does not contain space (equities, skip options like "AMZN 01/21/2028 ...").
   - Record: symbol, quantity, market_value.
   - Save list (e.g. to temp JSON or in-memory).

2. **Parse broker P/L % + P/L YTD from latest AccountStatement**
   - Locate most recent file: glob for `*AccountStatement*.csv` sorted by name/date, take last (2026- files preferred).
   - Read file, locate section starting with "Profits and Losses".
   - Parse header (Symbol,Description,P/L Open,P/L %,P/L Day,P/L YTD,P/L Diff,... Mark Value/Close Value).
   - For each subsequent row until next section:
     - If Symbol has no space (equity):
       - Extract P/L % (raw string, e.g. "+19.23%"), P/L YTD (raw "$3,766.90" or "($139k)"), Mark Value.
   - Build dict keyed by uppercase symbol.

3. **Compute YTD TWRR % for the equity symbols**
   - Preferred (post-recon): Use fast path.
     ```python
     from portfolio_analysis.twrr import get_capital_efficiency_twrr_report
     from portfolio_analysis.db import get_connection
     conn = get_connection()
     report = get_capital_efficiency_twrr_report(conn=conn, symbols=equity_symbols_list)
     ```
     - Build dict symbol -> twrr_ytd (the float % value).
   - Fallback for any missing/extreme: Use event-driven.
     ```python
     from portfolio_analysis.twrr import build_trade_driven_subperiods, compute_linked_twrr
     subs = build_trade_driven_subperiods(sym, conn)
     ytd = compute_linked_twrr(subs, "2026-01-01", "2026-05-27")
     ```
   - Filter out obvious garbage (e.g. |ytd| > 10000 or None). Log warnings for skipped.

4. **Merge datasets**
   - For each equity symbol that has BOTH TWRR and P/L data:
     - Combine: symbol, qty, mv (from holdings), ytd_twrr (from step 3), pl_pct_str, pl_ytd_str, mark_str (from step 2).
   - If a symbol has TWRR but no P/L (or vice versa), note it but include if possible (mark as N/A).

5. **Sort + render table**
   - Sort the list by ytd_twrr descending (highest first; Nones at bottom).
   - Print header:
     ```
     Symbol | Qty | Mkt Val | YTD TWRR% | Broker P/L % | P/L YTD $ | Mark Val
     ```
   - Use aligned printf-style or f-strings for readability (e.g. %-8s for symbol, right-align numbers).
   - At end: "Total positions shown: N"
   - Optional: Print top-3 summary line.

6. **Post-steps**
   - If any symbols had extreme TWRR or missing daily_twrr, recommend re-running the recon command above.
   - The output table is the final deliverable (markdown-friendly).

### Notes / Gotchas
- Always prefer daily_twrr path after recon (faster, validated). Fall back to subs only when needed.
- P/L % from broker is *not* the same as TWRR (open-lot % vs. time-weighted path on all capital). Document divergence if user asks.
- Handle parse quirks in AccountStatement (header variations like "Mark Value" vs "Close Value"; some rows have P/L Open as mark value — use header lookup + common-sense).
- Options are excluded (they appear in gt_daily_positions but have separate treatment).
- After full recon, re-run this workflow to get clean numbers.

Example invocation: `portfolio ytd-pl` (or in conversation paste a trigger phrase; the agent will run the CLI or equivalent).

The CLI command `portfolio ytd-pl` is the preferred way to invoke this (it uses the consolidated implementation in `src/portfolio_analysis/reporting.py`).

This workflow/CLI is the canonical way to answer "show me the full YTD picture for everything I hold, sorted by performance."

## Daily Position Quantity Reconstruction (for Charting) Workflow

**Trigger phrases:**
- "reconstruct daily positions for <symbol>"
- "show me clean position size series for <symbol>"
- "fix the position chart for <symbol>" / `portfolio daily-positions --symbol <SYM>`

**Purpose:** Produce a trustworthy continuous daily (date → shares) step series for a symbol to use in TWRR/price/position charts or diagnostics. Replaces direct queries to sparse `gt_daily_positions` or polluted `daily_position_values` (e.g. Journal internal adjustments treated as trades can create artificial quantity spikes).

The series always:
- Starts qty from the latest `gt_daily_positions` snapshot <= the window (or replays tx from dawn if none yet, so pre-window holdings are not lost).
- Applies *only* post-anchor Buy/Sell deltas.
- Completely ignores Journal tx (internal adjustments).
- Returns dense daily rows via reindex+ffill → perfect step function, no gaps/spikes/phantom zeros.

**Verification rule:** on GT snapshot dates, recon quantity must equal `gt_daily_positions`; on Journal-only days, quantity is carried (no inflation).

### Usage
```bash
portfolio daily-positions --symbol AAPL
portfolio daily-positions --symbol AAPL --start-date 2026-05-01 --end-date 2026-05-28
# Then pipe or save the table for charting, or use the dedicated chart:
portfolio chart twrr-ohlc-position --symbol AAPL --start-date 2026-05-01 --end-date 2026-05-28
```

The chart command produces a 3-panel PNG (top: cum TWRR from daily_twrr, mid: price, bottom: position step from the recon). It sources the bottom panel exclusively from the reliable recon (never raw daily_position_values/gt directly).

### In code (for agents)
```python
from portfolio_analysis.db import get_connection
from portfolio_analysis.daily_positions import reconstruct_daily_position_quantities
from portfolio_analysis.reporting import get_daily_position_series_for_symbol
conn = get_connection()
df = reconstruct_daily_position_quantities(conn, "AAPL", "2026-05-01", "2026-05-28")
# or the reporting wrapper (used by charts)
df = get_daily_position_series_for_symbol("AAPL", "2026-05-01", "2026-05-28", conn=conn)
print(df.tail())
# Compare recon qty to GT anchors for the symbol — never hard-code live sizes in docs.
```
Update SKILL.md when the CLI or recon contract changes.

See also `portfolio daily-positions --help` and the implementation in src/portfolio_analysis/daily_positions.py + charts.py + cli.py .

## Per-Symbol TWRR + OHLC + Position Size Chart Workflow

**Trigger phrases (use when user says these or close variants):**
- "run the twrr ohlc position chart for <symbol>" / "generate the symbol twrr chart for <symbol>"
- "show me the twrr price and position size chart for AAPL"
- "use portfolio chart twrr-ohlc-position for TSLA"
- "produce the dual panel TWRR/OHLC/position chart"

**Purpose:** Generate a 3-panel chart for one symbol:
- Top: Cumulative TWRR (from canonical daily_twrr after recon).
- Middle: Price (OHLC/close bars from local price cache).
- Bottom: Position size as a **clean step function** (from the anchored Journal-safe reconstruction, **never** raw queries against daily_position_values or sparse gt_daily_positions).

This is the chart generator updated to solve the overlapping tables problem (sparse GT + bad derived spikes from unfiltered Journal tx). Bottom panel is always a trustworthy step series with no anomalous spikes or long zero periods.

### Prerequisites (always do these first — DRY/MECE: data must be fresh GT + daily_twrr)
```bash
# 1. Ensure raw exports are ingested (implicit on most commands, but explicit is safer)
python tools/ingest_all_schwab_exports.py
python tools/ingest_account_statement_equities.py

# 2. Reconcile positions + daily_twrr (critical for correct anchors, clean qty series, and TWRR values)
# Use --loop for self-healing. Target the symbol(s) of interest.
python tools/build_reconciled_daily_positions.py \
    --symbols AAPL \
    --start-date 2026-05-01 \
    --end-date 2026-05-28 \
    --loop --max-iterations 2
```
- This snaps GT anchors, runs `reconstruct_daily_position_quantities` (anchored to latest gt_daily_positions, Journals filtered, full ffill), populates daily_twrr via subperiods + gapfill + boundary validation.

### Exact Workflow Steps (executable by agent)
1. Run the prerequisites above (recon is mandatory for trustworthy numbers and the clean bottom panel).
2. Invoke the dedicated CLI subcommand (preferred; consolidated under `portfolio`).
   ```bash
   portfolio chart twrr-ohlc-position \
       --symbol AAPL \
       --start-date 2026-05-01 \
       --end-date 2026-05-28 \
       --output /tmp/symbol_twrr_ohlc_pos.png
   ```
   - `--output` is optional (defaults to reports dir with timestamp).
   - Dates are optional (defaults derived from data).
3. Verify success:
   - Command exits 0 and prints "Chart saved to: ...".
   - PNG file exists and is non-empty.
   - Optional: `portfolio daily-positions --symbol AAPL …` and confirm quantities match GT anchors and Journal days do not inflate size.
   - The bottom panel of the PNG must visually be a step function (flat between real tx, jumps only on Buy/Sell, anchored at GT dates).

### In code (for agents / direct use)
```python
from portfolio_analysis.charts import generate_twrr_ohlc_position_chart
from pathlib import Path

chart_path = generate_twrr_ohlc_position_chart(
    symbol="AAPL",
    start_date="2026-05-01",
    end_date="2026-05-28",
    output_path=Path("/tmp/symbol_chart.png"),
)
print("Chart:", chart_path)
```

**Notes / Gotchas (DRY/MECE):**
- Always prefer `portfolio ...` subcommands over direct tool scripts.
- The position series for the bottom panel is produced by the single canonical implementation (`reconstruct_daily_position_quantities` in daily_positions.py). All consumers (CLI, charts, reporting wrapper) delegate to it. Do not query daily_position_values or gt_daily_positions directly for charting series.
- If the chart looks wrong (spikes, zeros, wrong final qty), the data is not reconciled — re-run the build tool.
- Options symbols are supported but price fetching may be thinner.
- Reports dir is `~/.portfolio-analysis/reports` (or `$PORTFOLIO_ANALYSIS_REPORTS_DIR` / `$PORTFOLIO_ANALYSIS_HOME`) — outside the git worktree.
- After new data drops, re-reconcile before generating charts.

Example invocation: `portfolio chart twrr-ohlc-position --symbol AAPL` (after recon).

The CLI + recon + chart generator are the canonical way to answer "show me the TWRR / price / position size chart for this symbol with a trustworthy clean step at the bottom."
