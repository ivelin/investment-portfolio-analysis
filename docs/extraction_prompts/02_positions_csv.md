# Extraction Template: Positions CSV Exports

**File type**: Bulk Schwab Positions export (e.g., `Account_Positions_2026-05-19.csv`)

**Primary target table**: `gt_daily_positions`

**Notes**: These files are relatively structured. While they can often be parsed programmatically, we still want a consistent high-quality extraction process for auditability.

## Recommended Approach

For these files, prefer **deterministic Python parsing** (using the helpers in `tools/ingest_positions_csv.py` and `src/portfolio_analysis/ingest.py`) over VQA, because the format is tabular and repeatable.

However, if you want an AI-assisted extraction for cross-validation, use the prompt below.

### Optional SOTA VQA Prompt (for verification only)

```
You are looking at a Schwab Positions CSV export.

Extract every active position row into the following JSON structure. Focus only on rows with positive quantity.

Output only valid JSON.

Schema:
{
  "source_file": "FILENAME.csv",
  "as_of_date": "YYYY-MM-DD",
  "positions": [
    {
      "symbol": "...",
      "quantity": 0,
      "avg_cost": 0,
      "market_value": 0,
      "unrealized_pl": 0
    }
  ]
}
```

Attach or paste the CSV content if the model supports it.
```

**Preferred method**: Use `tools/ingest_positions_csv.py` (and the supporting functions in `src/portfolio_analysis/ingest.py`).
