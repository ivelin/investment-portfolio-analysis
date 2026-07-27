# SOTA VQA Prompt Template: Brokerage Statement PDFs (TDA / Schwab)

**Purpose**: Highest-fidelity extraction for `gt_brokerage_statement_positions` to support accurate TWRR / capital efficiency reconciliation.

**Use only with frontier multimodal models** (Grok, Claude 3.5/Opus, GPT-4o, etc.). Do NOT use local pdfplumber or naive parsers.

---

## Prompt (Copy-Paste Ready)

```
You are an expert financial document analyst with state-of-the-art vision capabilities.

I have attached a TDA or Schwab brokerage statement PDF.

Your task is to extract **every single position** from the "Account Positions" section(s) with maximum precision. This data will be used as ground-truth position checkpoints for historical portfolio reconstruction and Time-Weighted Return calculations. Accuracy on quantities, market prices, market values, and cost basis is critical.

**Strict Requirements:**

- Extract ALL holdings shown (Stocks, ETFs, Mutual Funds, Options if present, etc.). Never omit or summarize.
- Use the statement's reporting period end date as the primary `as_of_date`.
- Preserve every number exactly as displayed. Do not round.
- If a field is blank or not present on the statement, omit the key or set it to null.
- Be especially careful with older TDA statement formatting.
- Pay close attention to any large positions or activity around 2022–2024.

Output **only** valid JSON matching this exact schema. No explanations, no markdown, no extra text.

```json
{
  "extraction_version": "1.0",
  "source_file": "EXACT-ORIGINAL-FILENAME.pdf",
  "extracted_by": "grok",
  "extracted_at": "2026-05-25T16:00:00Z",
  "statement_metadata": {
    "account_number": "...",
    "statement_period_start": "...",
    "statement_period_end": "...",
    "as_of_date": "...",
    "statement_type": "monthly",
    "source_firm": "TD Ameritrade"   // or "Charles Schwab"
  },
  "positions": [
    {
      "symbol": "...",
      "description": "...",
      "quantity": 0,
      "market_price": 0,
      "market_value": 0,
      "cost_basis": 0,
      "avg_cost": 0,
      "unrealized_gain_loss": 0,
      "estimated_annual_income": 0,
      "yield_pct": 0,
      "asset_class": "..."
    }
  ],
  "portfolio_summary": {
    "total_value": 0,
    "total_cost_basis": 0,
    "unrealized_gain_loss": 0
  },
  "notes": "Any observations about extraction difficulty, missing sections, or formatting quirks"
}
```

**File being processed**: [INSERT EXACT FILENAME HERE]

Process the attached PDF using your vision model and return only the JSON.
```

---

## Usage Instructions

1. Replace `[INSERT EXACT FILENAME HERE]` with the real filename (e.g., `TDA - Brokerage Statement_2023-12-31_052.PDF`).
2. Attach the full PDF.
3. For very long statements, you may need to process page-by-page and ask the model to merge.
4. After receiving the JSON, validate it manually for the symbol(s) you care most about (e.g., AAPL).
5. Ingest using:
   ```bash
   portfolio ingest-statement-data /path/to/extraction.json
   ```

---

## Recommended Variants

- **For reconciliation focus**: Add this sentence to the prompt:
  > "Prioritize perfect accuracy on quantity, market_value, and cost_basis fields. These will be used for position size reconstruction."

- **For 2023 TDA statements** (add this note):
  > "These older TDA statements often have complex table formatting. Use your strongest visual reasoning to correctly align columns."

This template is the only approved method for ingesting new brokerage statement data into the system.
