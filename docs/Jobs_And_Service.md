# Continuous jobs & service

**Status:** Local-first portfolio cache — hourly + client-forced **sync → derive → serve**

## Design (not a broker passthrough)

1. **Sync remote → local GT** (as much raw as the API/exports provide *now*)  
2. **Derive** daily NLV (and related) from **local** raw — maximize every reconstructible market day; label `ground_truth` / `live_exact` / `reconstructed`  
3. **Serve** clients from local raw + derived tables  

Remote broker API/MCP only **feeds the cache**. Multi-day NLV charts are **not** “call Schwab for 60 days.”

### Account NLV vs symbol tools (MCP clients)

| Question | Tool |
|----------|------|
| Account NLV over time / current IRA value | **`get_account_nlv_series_tool`** (`account` = display_name, `account_key`, or last-3 digits) |
| Shares of a ticker over time | `get_daily_positions_tool(symbol=TSLA)` |
| TWRR/OHLC chart for a ticker | `generate_twrr_ohlc_position_chart_tool(symbol=TSLA)` |

Hourly **`data_refresh`** always: sync remote→GT, **seed equity from local statement/positions exports** (Net Liquidating Value lines), then **maximize** local `daily_account_net_liq` from real anchors only (no flat carry-forward of last NLV; no fabrication of past NAV). Sparse series with provenance is correct when only monthly statements exist.
## Process model

| Mode | Entrypoint | Scheduler | MCP |
|------|------------|-----------|-----|
| **Continuous service** | `portfolio serve` / systemd | **On** (~hourly `data_refresh`) | Optional `--mcp-http` / `--mcp-stdio` |
| **One-shot CLI** | `portfolio jobs refresh` / `jobs run …` | **Off** | N/A |

Same pipeline for hourly and client force. `data_refresh` acquires flocks for `data_refresh` + `connector_sync` + `daily_net_liq` (fixed order); standalone jobs skip when `data_refresh` is held. Second trigger gets `already_running` (no duplicate sync/recalc).

All MCP clients share the same tools.

## Registered jobs

| Job id | Schedule | What it does |
|--------|----------|--------------|
| **`data_refresh`** | Hourly at **:05** | **Primary:** connector_sync → maximize local daily NLV (same as client force) |
| `daily_net_liq` | Hourly at **:35** (local top-up) | Re-derive NLV from local raw only (no remote) |
| `connector_sync` | On demand (+ inside data_refresh) | Broker → local GT only |

### Daily net-liq rules (hard)

1. Only **US equity market days** are candidates (weekends + major NYSE holidays excluded).
2. **Never stamp today’s live NAV onto past days** (fabrication is forbidden).
3. Reject non-finite and negative net-liq values.
4. When a **live** liquidation value is available for an as-of date, the stored daily row for that date **exactly equals** the live value (`provenance=live_exact`).
5. **Today is always reprocessed** on market days when using the legacy gap path so live can refresh the same-day row.
6. **Request-aware window:** `min_days` and/or `start_date`/`end_date`. After fill, coverage is assessed; if series length &lt; `min_days`, reason is **`insufficient_history`** (or `partial_coverage` when `on_insufficient=partial`) — not a silent complete success.
7. **Provenance on every row** (`daily_account_net_liq.provenance`):
   - `ground_truth` — from `gt_fund_equity_snapshots`
   - `live_exact` — from live broker/MCP snapshot (exact match)
   - `reconstructed` — from local positions / cash-flows (never live stamp)

### Source priority

1. Live snapshot for that exact date (exact match)  
2. GT fund equity snapshot  
3. Optional reconstruction (`allow_reconstruct`, default on for job runs): sum of `gt_account_positions.market_value` (+ cash when present on the same day), else prior GT anchor + external cash flows  

On days where both GT equity and reconstruction exist, the job **verifies** they match within a small tolerance and records mismatches for audit; storage prefers GT/live.

### On-demand refresh (same as hourly jobs — prefer for MCP clients)

```bash
# CLI: sync broker → GT, then daily net-liq
portfolio jobs refresh --force
portfolio jobs refresh --min-days 60 --on-insufficient partial

# Or step by step (same jobs the scheduler runs)
portfolio jobs run connector_sync --force
portfolio jobs run daily_net_liq --min-days 60 --pre-sync --force
```

MCP (recommended single call):

- **`refresh_portfolio_data_tool`** — `connector_sync` then `daily_net_liq`
- **`jobs_run_tool`** — `job_id=connector_sync` | `daily_net_liq` (poll with **`jobs_status_tool`**)
- **`jobs_list_tool`** / **`sync_status_tool`**

Responses include **`message`**, **`next_steps`**, and **`client_guidance`** so clients can:
- Report **current** NLV from latest sync without requiring 60 days of series
- Treat **`insufficient_history`** as “short history”, not “tool broken”
- Know to re-run refresh / wait for hourly sync / ingest exports

### CLI / MCP extras for `daily_net_liq`

```bash
portfolio jobs run daily_net_liq --min-days 60 --pre-sync --force
portfolio jobs run daily_net_liq --start-date 2026-01-01 --end-date 2026-07-28 --no-reconstruct
# on_insufficient: fail (default for jobs run) | partial (default for jobs refresh)
```

MCP `jobs_run_tool`: `min_days`, `start_date`, `end_date`, `pre_sync`, `allow_reconstruct`, `on_insufficient`.

## CLI

```bash
# One-shot connector sync (synthetic offline)
portfolio sync --demo --force
portfolio sync status

# Unified jobs API
portfolio jobs list
portfolio jobs run connector_sync --demo --force
portfolio jobs run daily_net_liq --force
portfolio jobs status connector_sync
portfolio jobs status --run-id <id>

# Continuous service (scheduler + optional MCP)
portfolio serve --mcp-http --port 3460
# Smoke (exits after registering jobs):
PORTFOLIO_ANALYSIS_SERVICE_SMOKE=1 python -m portfolio_analysis.service
```

## MCP tools (any client)

| Tool | Behavior |
|------|----------|
| `jobs_list_tool` | Catalog + last status |
| `jobs_run_tool` | Start job; default `background=true` returns `run_id` immediately |
| `jobs_status_tool` | Poll by `run_id` and/or `job_id` |
| `sync_connectors_tool` / `sync_status_tool` | Direct sync helpers (same core as `connector_sync`) |

Long runs never require a streaming MCP session: start → poll status.

## systemd (one unit)

Example user unit: `deploy/portfolio-analysis.service`

```bash
systemctl --user enable --now portfolio-analysis.service
```

Do **not** add one timer unit per job. schwab-mcp (broker auth) remains a separate dependency service when used.

## Data

- Instance home: `PORTFOLIO_ANALYSIS_HOME` (default `~/.investment-portfolio-analysis/`)
- Locks: `$PORTFOLIO_ANALYSIS_HOME/locks/{job_id}.lock`
- Status: `$PORTFOLIO_ANALYSIS_HOME/jobs/{job_id}_status.json`, `…/jobs/runs/{run_id}.json`
- Table: `daily_account_net_liq` (derived; regenerable from GT)

Status payloads never include tokens or client secrets.

## Manual MCP client check

```bash
# Preferred: user systemd unit (survives reboot)
systemctl --user enable --now portfolio-analysis.service
systemctl --user status portfolio-analysis.service

# Or one-off foreground
portfolio serve --mcp-http --host 127.0.0.1 --port 3460

# One-shot smoke (optional)
portfolio jobs list
portfolio jobs run connector_sync --force   # live connectors if configured
portfolio jobs run daily_net_liq --force
portfolio jobs status daily_net_liq
```

### URLs

| Client | URL |
|--------|-----|
| Local Streamable HTTP | `http://127.0.0.1:3460/mcp` |
| **Grok App / remote (Tailscale Funnel)** | `https://spark-9045.tail39d5a.ts.net/mcp/portfolio/mcp?apikey=$PORTFOLIO_MCP_KEY` |

`PORTFOLIO_MCP_KEY` lives in `~/.env` (gateway owner whitelist). MCP gateway (`mcp-gateway.service`) proxies `/mcp/portfolio` → `127.0.0.1:3460`.

Point any MCP client at the local or public URL. Use `jobs_run_tool` then poll `jobs_status_tool(run_id=…)`.

## Tests

Hermetic coverage lives in `tests/test_jobs.py` (shipped runners only):

- sequential multi-account connector sync + lock/`already_running`
- market-day gap fill; no fabricate without GT; reject non-finite/negative
- live exact match + **reprocess today** when last_saved == today
- `run_daily_net_liq` with injected adapters enforces live equality
- CLI `sync` / `jobs` + MCP tools + scheduler registration smoke
