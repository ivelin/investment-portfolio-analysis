# Extraction Template: Transactions XML Exports (Schwab)

**File type**: Schwab BrokerageHistoryResponse XML (`*Transactions*.xml`)

**Current landing table**: `transactions` (derived, lower fidelity)

**Warning**: This format has historically caused duplicate and date-formatting issues. Prefer the CSV version when available.

## SOTA VQA / XML Understanding Prompt

```
You are parsing a large Schwab Transactions XML export.

The root contains multiple <BrokerageTransaction> elements.

For each transaction, extract:

- Date
- Action
- Symbol
- Quantity
- Price
- Amount
- FeesAndCommission
- Description

Return a clean JSON array. Be extremely careful with date formats (normalize to YYYY-MM-DD if possible).

Output only JSON:

{
  "source_file": "FILENAME.xml",
  "transactions": [ ... ]
}
```

**Strong Recommendation**: 
- Use this only for cross-validation.
- Prefer ingesting the matching Transactions CSV into `gt_transactions` instead.
- After ingestion, run `recalculate_position_sizes()` to populate qty_before/qty_after using GT anchors.
