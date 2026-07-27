# Extraction Template: Realized Gain/Loss Lot Detail CSVs

**File type**: Schwab Realized Gain/Loss export (lot-level)

**Primary target table**: `gt_realized_gains`

**Notes**: These are critical for lot-level P/L history and can help with quantity reconstruction when statement snapshots are sparse.

## SOTA VQA Prompt (if needed for verification)

```
You are examining a Schwab Realized Gain/Loss CSV export.

Extract every realized lot into the following structure. Be precise with dates and dollar amounts.

Output only valid JSON.

{
  "source_file": "FILENAME.csv",
  "lots": [
    {
      "symbol": "...",
      "opened_date": "...",
      "closed_date": "...",
      "quantity": 0,
      "cost_basis": 0,
      "proceeds": 0,
      "gain_loss": 0,
      "term": "short" or "long",
      "wash_sale": "..."
    }
  ]
}
```

## Preferred Ingestion Method

Use the dedicated ingestion logic in `tools/ingest_all_schwab_exports.py` (and supporting functions in `src/portfolio_analysis/ingest.py`).

These files are best handled with structured CSV parsing rather than vision models unless the file is unusually messy.
