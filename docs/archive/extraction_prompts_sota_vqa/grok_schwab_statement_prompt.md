# Grok Schwab Brokerage Statement Extraction Prompt

**Goal**: Extract all positions from a Schwab (or TDA) brokerage statement PDF into structured JSON that can be ingested via `ingest_brokerage_statement_reconciled()`.

## Instructions for Grok

You are given a Schwab brokerage statement PDF. Extract the **Account Positions** section with maximum accuracy.

Output **only** valid JSON matching this exact schema:

```json
{
  "statement": {
    "account_number": "string or null",
    "as_of_date": "YYYY-MM-DD",
    "statement_period_start": "YYYY-MM-DD or null",
    "statement_period_end": "YYYY-MM-DD or null"
  },
  "positions": [
    {
      "symbol": "AAPL",
      "quantity": 10.0,
      "market_price": 100.00,
      "market_value": 1000.00,
      "cost_basis": 900.00,
      "page": 3
    }
  ]
}
```

### Rules

- Include **every** stock, ETF, and mutual fund position with quantity > 0.
- Ignore cash, money market funds, and pending transactions.
- Use the **as_of_date** from the statement header if available.
- Extract numbers exactly as shown (do not round).
- If a field is missing, use `null`.

## Example Usage

After Grok returns the JSON, save it and run:

```bash
python -c "
from src.portfolio_analysis.db import get_connection
from src.portfolio_analysis.ingest import ingest_brokerage_statement_reconciled
import json
from pathlib import Path

conn = get_connection(Path.home() / '.portfolio-analysis' / 'portfolio.db')
with open('2026-04-30_extraction.json') as f:
    data = json.load(f)

count = ingest_brokerage_statement_reconciled(conn, grok_extraction=data)
print(f'Ingested {count} positions')
conn.close()
"
```

This is the highest-fidelity path for TWRR anchor data.
