# Documentation Index

This directory contains the detailed specifications, workflows, and design documents for the portfolio-analysis project.

**Origin story (why the project exists):** keep retail investors honest about their own portfolio and per-account performance by treating personal accounts as **retail private funds** and applying the same objective rules used on public stocks/ETFs/funds (technical averages, CANSLIM-class discipline, cash-flow-neutral TWRR). See the root [README.md](../README.md) and [Fund_As_Symbol_Design.md](Fund_As_Symbol_Design.md).

**Guiding Principles (DRY + MECE)**
- Each major topic has **one primary source of truth**.
- Information is not duplicated across files.
- Cross-references point to the canonical document instead of repeating content.

## Quick Navigation

### For Agents & Skill Users
- [SKILL.md](../SKILL.md) — Authoritative interface for using this as a Grok skill (CLI commands, constraints, recommended workflows).
- [README.md](../README.md) — Project overview and quick start.

### Core Workflows & Data Handling (Single Source of Truth)
- **[Ingestion-Workflow.md](Ingestion-Workflow.md)** — **The canonical reference** for all data sources, file types, ingestion commands, canonical storage rules, and recommended processes.
  - Includes detailed guidance on Positions CSVs, AccountStatement CSVs, Transactions, Realized Gains, and PDF statements.
  - Contains the complete file type matrix and master ingestion scripts.

### Design & Implementation Specifications
- [Capital_Efficiency_Daily_TWRR_Design.md](Capital_Efficiency_Daily_TWRR_Design.md) — High-level design for the Daily TWRR Capital Efficiency system and the event-driven reconstruction approach.
- [TWRR_Daily_Implementation_Plan.md](TWRR_Daily_Implementation_Plan.md) — Phased implementation plan for the daily TWRR engine.
- [INGESTION_AND_RECONCILIATION_FRAMEWORK.md](INGESTION_AND_RECONCILIATION_FRAMEWORK.md) — Detailed framework for ingestion strategies, GT anchor fidelity, daily position reconstruction, and self-healing reconciliation loops (includes the full export type matrix).
- [Fund_As_Symbol_Design.md](Fund_As_Symbol_Design.md) — Private fund-as-symbol: account-level TWRR growth index, multi-broker adapters, MA stack / under-MA alerts.

### Statement Extraction Prompts (Retired PDF/SOTA VQA Path)
The primary PDF + SOTA VQA extraction route for brokerage statements was retired in favor of direct structured Schwab CSV/XML/JSON exports (see INGESTION_AND_RECONCILIATION_FRAMEWORK.md for policy and the single historical note). The original SOTA prompt is archived.

- [extraction_prompts/](extraction_prompts/) — Active guidance for direct structured exports:
  - `02_positions_csv.md`
  - `03_realized_gains_csv.md`
  - `04_transactions_csv.md`
  - `05_transactions_xml.md`
  - `06_1099r_tax.md`

The retired SOTA VQA prompt lives in `archive/extraction_prompts_sota_vqa/01_brokerage_statements_sota_vqa.md`. The two grok_*.md files in this directory are historical.

## How Documentation Is Organized

| Audience                  | Primary Document                  | Purpose |
|---------------------------|-----------------------------------|-------|
| Agents / Skill users      | `SKILL.md` (root)                 | How to invoke and work with this skill |
| Developers & contributors | `README.md` (root) + this index   | Project overview + navigation |
| Anyone doing ingestion    | `Ingestion-Workflow.md`           | **Single source of truth** for data handling |
| Architects & long-term work | Design & Framework docs        | Rationale, architecture, and implementation plans |

## Updating Documentation

- When changing ingestion behavior or data sources → update **Ingestion-Workflow.md** first.
- When changing the public CLI or skill interface → update **SKILL.md**.
- When changing high-level design → update the relevant design document and add a note here if needed.
- Always prefer **linking** to the canonical document rather than copying content.

This structure keeps the documentation DRY (Don't Repeat Yourself) and MECE (Mutually Exclusive, Collectively Exhaustive).
