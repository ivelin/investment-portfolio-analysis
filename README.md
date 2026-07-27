# Portfolio Analysis

Personal portfolio analysis tool focused on the CANSLIM system, capital efficiency, and **honest self-accountability**.

## Why this exists (origin story)

Retail investors often apply strict rules to the **public** instruments they buy — stocks, ETFs, and funds — then go soft on the one “manager” they cannot fire: **themselves**.

This project exists to keep a retail investor (the author, and anyone who runs it locally) **objectively honest** about portfolio and **per-account** performance. Whatever discipline you apply to market symbols — technical averages (21 EMA, 50 DMA, 200 DMA), stack structure, quarterly/annual earnings quality, return on equity, PnL, CANSLIM-style keep/weed rules — you should be able to apply the **same class of objective measurement** to your own accounts as **retail private funds**.

- **Per-symbol capital efficiency (TWRR)** answers: is this *holding* earning its keep?
- **Fund-as-symbol (account-level TWRR index)** answers: is *this account / this manager (me)* earning its keep after deposits and withdrawals are neutralized?

No fabricated history. Incomplete truth over comforting fiction. Local data only — the repository is safe to open-source; your balances and exports stay on your machine under the **canonical instance home** `~/.investment-portfolio-analysis/` (`PORTFOLIO_ANALYSIS_HOME`). See [SECURITY.md](SECURITY.md). Tracked fixtures under `tests/fixtures/extractions/` are synthetic placeholders only.

## Features

- Ingest Schwab realized gains and transaction exports
- Calculate time-weighted capital efficiency per symbol
- Treat each brokerage account as a **private fund symbol** (`portfolio fund …`) with cash-flow-neutral TWRR index, EMA21 / SMA50 / SMA200, and under-MA alerts
- Generate "Weed the Garden" reports with Keep / Monitor / Weed recommendations
- Professional visualization and PDF reporting
- Period filtering (YTD, specific year, last N months, etc.)

## Installation

```bash
cd portfolio-analysis
uv sync
uv pip install -e .
```

## Usage

### Generate Text Report

```bash
portfolio report --year 2026
portfolio report --period ytd
portfolio report --period last-6-months
```

### Generate Position Size Distribution Chart

```bash
portfolio chart distribution \
    --positions /path/to/Schwab_Positions.csv \
    --output /tmp/portfolio-analysis-reports/distribution.png
```

### Generate Professional PDF Report

```bash
portfolio pdf-report \
    --positions /path/to/Schwab_Positions.csv \
    --output /tmp/portfolio-analysis-reports/Portfolio_Analysis_Report.pdf
```

All reports and charts are written under `~/.investment-portfolio-analysis/reports/` by default (or `PORTFOLIO_ANALYSIS_REPORTS_DIR` / `PORTFOLIO_ANALYSIS_HOME`). This keeps the git worktree clean and keeps balance-bearing artifacts with the rest of your private instance data.

The PDF report includes:
- Clean executive summary
- High-quality dual-axis position size distribution chart
- Key observations
- Professional typography and layout

### Ingest Daily Positions for Capital Efficiency (Daily TWRR)

```bash
portfolio ingest-positions \
    --positions /path/to/Schwab_Positions.csv \
    --as-of 2026-05-20
```

This is the foundation for the new **Daily Time-Weighted Rate of Return (TWRR)** Capital Efficiency indicator (see `docs/Capital_Efficiency_Daily_TWRR_Design.md`). It is 100% additive — existing `portfolio report` and Weed the Garden output are unchanged.

**CRITICAL — HARD RULE (Data Integrity)**

This tool **strictly and permanently** follows a zero-tolerance policy on data quality:

- **NEVER** uses simulated, made-up, interpolated, backfilled, or fabricated daily values for Capital Efficiency or TWRR calculations.
- **ONLY** real, verified data from actual Schwab Positions exports or the Schwab API is accepted.
- If there is insufficient real daily data, the system will clearly tell you instead of producing misleading numbers.

This rule exists because early experiments with reconstructed data produced dangerously wrong performance figures. It will never be relaxed.

**Important**: This skill uses **only ground truth data** from your actual brokerage exports. No simulated or fake data is ever used.

## Philosophy

This tool is designed to help you:
- Hold **yourself** to the same objective bar you use on public stocks, ETFs, and funds
- Identify which positions — and which **accounts** — are truly working
- Make data-driven decisions about adding to or exiting positions
- Improve capital allocation over time using principles similar to top CANSLIM traders

**Data Integrity is Sacred**
Capital allocation decisions are too important to be based on anything less than real, verified brokerage data. The system will always prefer incomplete truth over comforting fiction. When real daily position history is missing, it will guide you to provide it rather than invent numbers.

### Private fund (account) demos

Safe synthetic path (no real balances required):

```bash
portfolio fund rebuild --demo
portfolio fund series --symbol FUND:synthetic:demo01
portfolio fund mas --symbol FUND:synthetic:demo01
portfolio fund alerts --symbol FUND:synthetic:demo01
```

See [docs/Fund_As_Symbol_Design.md](docs/Fund_As_Symbol_Design.md).

### Local CI

```bash
make ci   # ruff + full pytest suite
```

**Ingestion is Automatic (Implicit Prerequisite)**
You no longer need to manually run ingestion commands in normal usage.

When you run `portfolio report`, `portfolio twrr`, or any analysis feature, the system will automatically:
- Check for sufficient real Schwab data in the local database
- Discover and ingest new real export files from common locations if needed
- Only then produce results

See [docs/Ingestion-Workflow.md](docs/Ingestion-Workflow.md) for full details.

**For Hermes / OpenClaw / Agent Usage**: The authoritative CLI reference and expected behavior is documented in [SKILL.md](SKILL.md). This is what the skill should use when invoking the `portfolio` tool.

## Portfolio Data Sources (Canonical Location)

This tool has **no hardcoded "watched directory"**. You always explicitly pass the path to your Schwab export files when ingesting.

### Recommended Canonical Storage

**Primary Ground Truth Directory (Hard Rule)**

Raw broker exports live under the instance home **outside the repo**: preferred layout `~/.investment-portfolio-analysis/exports/{schwab,ibkr,robinhood,fidelity}/` (legacy flat `~/.investment-portfolio-analysis/schwab-exports/` still works for Schwab). The agent **must never** delete, move, rename, or modify files in those directories. List adapters with `portfolio brokers list`.

For the full recommended folder structure and rationale, see:
[docs/Ingestion-Workflow.md → Recommended Canonical Storage](docs/Ingestion-Workflow.md#recommended-canonical-storage)

### File Types & Ingestion

See the detailed, authoritative reference: [docs/Ingestion-Workflow.md](docs/Ingestion-Workflow.md#files-you-must-ingest)

**Current supported commands** (as of May 2026):
```bash
portfolio ingest-positions --positions ... --as-of YYYY-MM-DD
python tools/ingest_account_statement_equities.py   # monthly Account Statements
```

### Hard Rule Reminder

Only files that are **direct exports from Schwab** (CSV or official XML responses) are accepted. The system will never fabricate or interpolate daily position data for Capital Efficiency calculations.

See [docs/Ingestion-Workflow.md](docs/Ingestion-Workflow.md) for the complete file type matrix, master scripts, and workflows.

Detailed design and framework documentation lives in the [docs/](docs/) directory (start with [docs/README.md](docs/README.md) for the index).

## Manual Mode

Currently runs in manual mode. You control when to ingest new exports and when to run reports.

## License

Copyright 2025–2026 Ivelin Ivanov

Licensed under the **Apache License, Version 2.0** (the "License"). You may not use this project except in compliance with the License. See the [LICENSE](LICENSE) file and [NOTICE](NOTICE) for details.

```text
http://www.apache.org/licenses/LICENSE-2.0
```

Personal brokerage data, tokens, and balances must never be committed; they stay under `PORTFOLIO_ANALYSIS_HOME` (see [SECURITY.md](SECURITY.md)).
