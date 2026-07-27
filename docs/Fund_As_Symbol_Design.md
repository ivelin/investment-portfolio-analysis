# Fund-as-Symbol Design

**Status:** Multi-broker GT + daily net-liq/TWRR index + TA charts (import/rebuild/chart CLI)
**Data integrity:** Same hard rule as Capital Efficiency / Daily TWRR — **no fabricated bars**.

## Origin / purpose

Retail investors already grade **public** stocks, ETFs, and funds with objective rules (21 EMA, 50/200 DMA, MA stack, earnings, ROE, PnL, CANSLIM-style keep/weed). The hard part is applying that same honesty to **their own accounts** — the retail private funds they effectively manage.

This feature treats each brokerage **account** (later: combined book) as a **private fund symbol** so the operator can measure **manager skill** with:

1. A cash-flow-neutral **TWRR growth index** (deposits/withdrawals do not masquerade as skill)
2. A **net liquidation value** series (account “price”) for the same technical stack used on equities

Deposits and withdrawals must never masquerade as performance. Sparse real history is OK; invented bars are not.

## Non-goals

- Live order placement (use broker MCPs for trading).
- Per-holding-symbol TWRR (already in `twrr.py` / `daily_twrr`).
- Inventing history to satisfy 200 DMA.
- Committing balances, tokens, or exports to git.
- Full fundamental data model for “fund earnings/ROE” (document reasoning workflow only).

## Layers (MECE)

1. **Connectors / adapters** (`connectors/`, `brokers/`, `brokers/sources/`) — normalize accounts, equity snapshots, cash flows, positions from MCP/API/exports.
2. **Ground truth** — immutable broker-agnostic tables:
   - `gt_fund_accounts`
   - `gt_fund_equity_snapshots` (net liquidation per day)
   - `gt_fund_cash_flows` (external CF only)
   - `gt_account_positions` (uniform multi-broker holdings)
3. **Derived** — `fund_daily` (regenerable): `liquidation_value` + `twrr_index` + `daily_return` + `external_cf`.
4. **Technicals / alerts** — pure functions on series (`twrr_index` or `liquidation_value`).
5. **Charts / CLI / MCP** — operator surfaces.

## Uniform multi-broker account & positions schema

| Table | Role | Key |
|-------|------|-----|
| `gt_fund_accounts` | Account identity | `(broker, account_key)` |
| `gt_fund_equity_snapshots` | Point-in-time net liq | `(broker, account_key, as_of_date, source)` |
| `gt_fund_cash_flows` | External deposits/withdrawals/ACATS | broker + key + date + type |
| `gt_account_positions` | Holdings | `(broker, account_key, as_of_date, symbol, source)` |
| `fund_daily` | Daily indexed series | `(fund_symbol, as_of_date)` |

`account_key` is a stable hash of the broker-native id (never log full account numbers).
`fund_symbol` = `FUND:{broker}:{account_key}`.

Schwab imports via connector live source (MCP/API) or synthetic demo. The same GT tables accept IBKR/RH when adapters land.

## Fund symbol naming

| Kind | Form | Example |
|------|------|---------|
| Per account | `FUND:{broker}:{account_key}` | `FUND:schwab:a1b2c3d4` |
| Combined book (later) | `FUND:ALL` | — |

## TWRR growth index (“skill price”)

- Start index at **100** on the first day with a usable equity snapshot.
- **External cash flows** adjust the capital base:

  \[
  r_t = \frac{V_t}{V_{t-1} + CF_t} - 1, \quad I_t = I_{t-1}\cdot(1+r_t)
  \]

- **Net liquidation** \(V_t\) is stored every day for NAV-style charts.
- Days without a new snapshot: **no synthetic fill** (sparse series OK).

## Technical rules

| Signal | On TWRR index (alerts default) | On net liq (chart default) |
|--------|--------------------------------|----------------------------|
| EMA 21 | yes | yes |
| SMA 50 | yes | yes |
| SMA 200 | yes | yes |
| Bullish stack | EMA21 > SMA50 > SMA200 when all defined | same |
| Insufficient history | MA = undefined; alert may fire `insufficient_history` | chart omits MA + footnote |

## Multi-broker adapters

| Broker | Status | Notes |
|--------|--------|--------|
| `synthetic` | ready | Demo/tests; long history for SMA200 charts |
| `schwab` | live_capable | Connectors: local/remote MCP or direct OAuth; positions via get_accounts |
| `ibkr` / `robinhood` / `fidelity` | planned | Stubs + reserved export dirs |

Configure: `portfolio connectors …` or MCP `configure_connector_tool`.
Import: `portfolio fund import --broker schwab` or `--demo`.

## Operator workflow (examples)

```bash
# Offline pressure path (no private credentials required)
portfolio fund import --demo
portfolio fund series --symbol FUND:synthetic:demo01
portfolio fund mas --symbol FUND:synthetic:demo01 --price-field liquidation_value
portfolio fund chart --symbol FUND:synthetic:demo01 --price-field liquidation_value
portfolio fund chart --symbol FUND:synthetic:demo01 --price-field twrr_index

# Live Schwab (requires connector + working MCP/OAuth)
portfolio connectors test schwab
portfolio fund import --broker schwab
portfolio fund chart --symbol FUND:schwab:<account_key> --price-field liquidation_value
```

Charts write under `$PORTFOLIO_ANALYSIS_HOME/reports/` by default (never the git tree).

## Fundamentals reasoning (as if professionally managed)

Treat the account like a fund/ETF symbol:

- **Price / NAV path:** net liquidation series + MA stack (this package).
- **Manager skill:** TWRR index path (CF-neutral) + under-MA alerts.
- **Capital efficiency of holdings:** existing per-symbol `daily_twrr` / Weed-the-Garden.
- **Earnings / ROE of the “manager”:** not a separate data model here — reason qualitatively from TWRR vs benchmarks and concentration in `gt_account_positions`.

## Local data only

All instance data lives under `PORTFOLIO_ANALYSIS_HOME` (default `~/.portfolio-analysis/`). See [SECURITY.md](../SECURITY.md) and `src/portfolio_analysis/paths.py`. No real broker payloads in the repository.
