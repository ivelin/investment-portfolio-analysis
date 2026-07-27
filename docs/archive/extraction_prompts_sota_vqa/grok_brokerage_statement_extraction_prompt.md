# Grok Prompt Template: Brokerage Statement Extraction

Use this prompt (or a close variant) when you want the highest-quality structured extraction from a TDA/Schwab brokerage statement PDF. The goal is to produce output that can be directly fed into `ingest_brokerage_statement_data()` and stored in `gt_brokerage_statement_positions`.

---

**System / User Prompt:**

You are an expert financial document parser with access to the attached PDF.

Your task is to extract **every** position from the "Account Positions" section(s) of this brokerage statement and return it in the exact JSON structure defined below.

**Rules:**
- Extract **all** holdings shown on the statement (Stocks, Mutual Funds, ETFs, etc.). Do not filter or summarize.
- Use the statement's reporting period end date as `as_of_date` whenever possible.
- Preserve numbers exactly as shown (do not round).
- If a field is missing on the statement, omit the key or set it to null.
- Output **only** valid JSON. No extra commentary.

**Required Output Schema (version 1.0):**

```json
{
  "extraction_version": "1.0",
  "source_file": "original-filename.pdf",
  "extracted_by": "grok",
  "extracted_at": "2026-05-22T14:30:00Z",
  "statement_metadata": {
    "account_number": "999-000001",
    "statement_period_start": "2022-04-01",
    "statement_period_end": "2022-04-30",
    "as_of_date": "2022-04-30",
    "statement_type": "monthly",
    "source_firm": "TD Ameritrade"
  },
  "positions": [
    {
      "symbol": "AAA",
      "description": "SYNTHETIC CORP A",
      "quantity": 10,
      "market_price": 100.00,
      "market_value": 1000.00,
      "cost_basis": 900.00,
      "avg_cost": 90.00,
      "unrealized_gain_loss": 100.00,
      "estimated_annual_income": 0,
      "yield_pct": 0,
      "asset_class": "Stock"
    }
    // ... every other position on the statement ...
  ],
  "portfolio_summary": {
    "total_value": 1750.00,
    "total_cost_basis": 1580.00,
    "unrealized_gain_loss": 170.00
  },
  "notes": "Example uses synthetic values only — never paste real account balances into public docs"
}
```

After you return the JSON, I will validate it and insert it into the ground-truth database using the official schema.

---

**Tips for best results with Grok**

- Attach the full PDF.
- For very long statements, you can ask Grok to process page-by-page and then combine the results.
- If Grok misses a section, say: "You missed the Mutual Funds section on page 5. Please extract those positions as well using the same schema."
- For reconciliation quality, ask Grok to be extremely precise with numbers and to include every symbol shown.

This format guarantees that every statement you extract becomes high-fidelity, auditable ground truth in `gt_brokerage_statement_positions`. Redundant data across multiple statements is intentionally kept for cross-validation and reconstruction testing.
