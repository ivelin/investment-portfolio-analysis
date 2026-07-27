## Schwab Positions CSV Format (2026-05)

Schwab "Positions" exports have a non-standard structure that breaks naive csv.DictReader:

- Line 1: Title row (e.g. "Positions for account <Account Name> ... as of ...")
- Line 2: Blank
- Line 3: Real header row with quoted columns including "Qty (Quantity)", "Mkt Val (Market Value)", "Gain $ (Gain/Loss $)", etc.

**Required handling**:
- Always skip first 2 lines before DictReader.
- Quantity column name is "Qty (Quantity)" (not "Quantity").
- Market value column is "Mkt Val (Market Value)".
- Use flexible matching or exact name for robustness.

**Fallback pattern when DB `positions` table is empty**:
- The `generate_weed_the_garden_report` relies on DB join and may return 0 active rows.
- In pdf_report.py, detect empty active_report and fall back to direct CSV read for the table (same parser as charts.py).
- This guarantees the table shows real current positions even if ingestion lagged.

**Pitfall**: Ingest functions must use the same skip-2-lines logic or they silently insert 0 rows. Always verify row count after ingest_positions.

This pattern emerged during repeated "table missing data" debugging and is now the standard approach for Schwab position snapshots.
