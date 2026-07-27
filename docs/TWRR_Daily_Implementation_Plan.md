# Daily Time-Weighted Rate of Return (TWRR) Implementation Plan

**Version:** 1.1
**Date:** 2026-05-29
**Owner:** Ivelin Ivanov
**Status:** Updated for Two-Phase Daily TWRR Population (Boundary + Gapfill with Consistency Validation)
**Key Change:** Phase 2 now explicitly fills calendar days using price-driven returns + residual adjustment on boundaries for exact HPR consistency + validation of intermediate events.

---

## Objective

Build a production-grade, auditable daily TWRR calculation system that correctly handles dynamic position resizing, corporate actions, and cash flows. The system will store daily TWRR values and provide rolling 30-day TWRR (and other periods) as the primary capital efficiency trend signal.

**No EMA.** Focus is on rolling 30-day TWRR as the main trend indicator.

---

## Reference Implementation

- **Primary Reference**: R package `PerformanceAnalytics`
  - Functions: `TimeWeightedReturn()`, `TWR()`, `Return.portfolio()`
  - Sub-period creation logic at external cash flows
  - Geometric linking methodology
- Secondary references:
  - GIPS (Global Investment Performance Standards) – CFA Institute
  - CFA Level 1 & 3 curriculum on Time-Weighted vs Money-Weighted returns

---

## Factors That Must Be Explicitly Accounted For

The implementation must correctly handle all of the following:

1. **External Cash Flows** — Deposits, withdrawals, transfers (must trigger sub-period split)
2. **Stock Splits & Reverse Splits** — Adjust shares and price, do not create return
3. **Stock Dividends** — Treat as reinvestment (increase shares)
4. **Cash Dividends** — Option to treat as external flow or reinvested
5. **Mergers & Acquisitions** — Proper adjustment or position termination
6. **Spin-offs** — Create new position or treat as cash flow
7. **Rights Issues & Warrants** — Adjust cost basis or treat as separate instrument
8. **Tender Offers & Buybacks** — Record as external cash flow
9. **Options & Derivatives** — Track independently from underlying
10. **Partial Fills & Multi-day Settlements** — Attribute to correct valuation date
11. **Corporate Action Timing** — Consistent ex-date vs payment date rules
12. **Zero or Negative Capital Days** — Graceful handling, no division by zero
13. **Position Closure & Re-opening** — Treat as separate capital cycles
14. **Currency Effects** — Local vs reporting currency decision
15. **Missing Price Data** — Defined fallback rules
16. **Valuation Timing** — Standardize on End-of-Day pricing
17. **Wash Sales & Tax Lots** — Decide position-level vs lot-level calculation

---

## Detailed Implementation Phases

### Phase 1: Data Model & Ingestion

**Tables to create:**
- `daily_position_values`
- `position_cash_flows`
- `corporate_actions`
- `daily_twrr`
- `rolling_twrr`

**Ingestion Requirements:**
- Import daily/periodic position snapshots from Schwab exports (dedicated Positions CSVs + monthly AccountStatement CSVs)
- Classify every transaction as external cash flow or corporate action
- Automatically apply corporate action adjustments

### Phase 2: Daily TWRR Calculation Engine (Two-Phase Population)

**Core Principle:** Single source of truth for all HPR math — the event-driven subperiod builder (`build_trade_driven_subperiods`). Both detailed breakdowns and the fast `daily_twrr` table are derived from it.

**Phase 2a — Boundary Population (Authoritative)**
- Function: `populate_daily_twrr_from_subperiods(symbol)`
- For each sub-period produced by the engine, insert one row in `daily_twrr` on the `end_date` with `daily_return = subperiod.hpr`.
- Use `calc_version = 'subperiod-hpr-v1'`.
- This is the only place the true HPR is ever computed.

**Phase 2b — Gap Filling + Validation (for Dense Usable Series)**
- Function: `fill_daily_twrr_gaps(symbol)`
- For every calendar day inside a subperiod window:
  - Use actual daily closing prices to compute realistic price-driven returns on intermediate days.
  - On the subperiod end boundary, solve for the exact residual return so the geometric product of **all** daily returns in the window equals the original subperiod HPR (within 1e-10 tolerance).
- **Built-in Validation (Mandatory):**
  - Re-compound the filled daily series for the window and assert exact match to subperiod HPR.
  - Scan for any unaccounted position-changing events or dividends strictly inside the subperiod (should have been handled by the builder).
  - Fail the reconciliation pass loudly on violations.
- Intermediate rows use `calc_version = 'subperiod-hpr-v1-gapfill'` and slightly lower `data_quality`.

**Why this model?**
- Keeps calculation DRY/MECE (one HPR engine).
- Delivers a dense daily series for fast, efficient reporting and arbitrary window compounding.
- Enforces that cumulative TWRR from the daily series exactly matches boundary subperiod values at every trade/event date.
- Makes intermediate dividends, corporate actions, and price moves visible and validated.

**Core Functions (updated):**
- `build_trade_driven_subperiods` (authoritative engine)
- `populate_daily_twrr_from_subperiods`
- `fill_daily_twrr_gaps` (with validation)
- `calculate_daily_twrr` (now prefers the populated `daily_twrr` table; errors with reconciliation guidance if insufficient authoritative data)

### Phase 3: Storage & Incremental Updates

- Store daily TWRR with metadata (sub-period count, cash flow flags, data quality)
- Store pre-computed rolling 30-day TWRR
- Incremental daily updates only

### Phase 4: Analytics Layer (No EMA)

- Rolling 30-day TWRR as primary capital efficiency trend signal
- Support for 60-day, 90-day, YTD, and custom periods via geometric linking
- Query capability for efficiency trend (rising/falling)
- Clean data structures prepared for charting

### Phase 5: Testing & Validation

- Unit tests for all 17 factors
- Reconciliation against known periods
- Edge case testing (zero capital, same-day flows, corporate actions)
- Backtesting on real positions with resizing activity
- Comparison with R `PerformanceAnalytics` output where possible

### Phase 6: Documentation & Handover

- Technical specification document
- Data dictionary
- Calculation methodology (GIPS/CFA aligned)
- Example walkthroughs using real positions
- Maintenance and monitoring guide

---

## Success Criteria

- Daily TWRR behavior matches R `PerformanceAnalytics` within acceptable tolerance
- Rolling 30-day TWRR is the primary capital efficiency trend signal
- All 17 factors are handled without manual intervention
- All calculations are deterministic and reproducible

---

## Next Steps

1. Finalize database schema (Phase 1)
2. Build daily TWRR calculation prototype on 2–3 real positions
3. Proceed with full implementation once prototype is validated

---

*This plan has been superseded by the polished & fleshed-out design specification:*

**→ [Capital_Efficiency_Daily_TWRR_Design.md](./Capital_Efficiency_Daily_TWRR_Design.md)**

The design document expands every phase, adds concrete schemas, algorithm details, a full PR plan, Key Decisions, data acquisition contract, calibration requirements, and addresses all 17 factors with traceability. It is the authoritative reference for implementation.
