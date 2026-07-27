# Extraction Template: Transactions History CSVs

**File type**: Schwab Transactions / Activity CSV export

**Primary target table**: `gt_transactions`

## Notes
This is the preferred path for transaction history (cleaner than the XML version).

## SOTA VQA Prompt (rarely needed)

```
Extract every transaction row from this Schwab Transactions CSV.

Return only valid JSON:

{
  "source_file": "FILENAME.csv",
  "transactions": [
    {
      "transaction_date": "...",
      "symbol": "...",
      "transaction_type": "...",
      "quantity": 0,
      "price": 0,
      "amount": 0,
      "fees": 0,
      "description": "..."
    }
  ]
}
```

## Preferred Method
Use `ingest_transactions()` from `portfolio_analysis.ingest` (lands in `gt_transactions` with proper deduplication).
