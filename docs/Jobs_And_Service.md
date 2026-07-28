# Continuous jobs & service

**Status:** Continuous service + two staggered hourly jobs (connector sync, daily net-liq)

## Process model

| Mode | Entrypoint | Scheduler | MCP |
|------|------------|-----------|-----|
| **Continuous service** | `portfolio serve` / `python -m portfolio_analysis.service` / systemd | **On** | Optional `--mcp-http` and/or `--mcp-stdio` |
| **One-shot CLI** | `portfolio sync`, `portfolio jobs run …` | **Off** | N/A |

Transport (stdio vs HTTP) does **not** decide the scheduler. Lifetime does: long-lived service vs exit-after-command CLI.

All MCP clients (Grok App, IDE plugins, agents, etc.) share the same tools. There is no client-specific branching.

## Registered jobs (staggered hourly)

| Job id | Schedule | What it does |
|--------|----------|--------------|
| `connector_sync` | Hourly at **:05** | Walk enabled brokers **sequentially**, then each account sequentially; persist accounts / equity / positions into local GT. Never fabricates balances. |
| `daily_net_liq` | Hourly at **:35** | From **local** `gt_fund_equity_snapshots`, gap-fill `daily_account_net_liq` from last saved date through today. |

### Daily net-liq rules (hard)

1. Only **US equity market days** are candidates (weekends + major NYSE holidays excluded).
2. **Never invent** a day without a real local GT equity snapshot (or live value for that exact date).
3. Reject non-finite and negative net-liq values.
4. When a **live** liquidation value is available for an as-of date, the stored daily row for that date **exactly equals** the live value (`source=live_exact`).
5. **Today is always reprocessed** on market days (even if a row already exists), so a later live snapshot overwrites a same-day GT value. Historical gap days still start after `last_saved` and are never filled with today’s live figure.

Historical gap days use local GT only — today’s live value is **not** stamped onto past days.

On the real path, `daily_net_liq` **best-effort loads enabled live connectors** (same resolution as `connector_sync`) so exact match works without manual adapter injection. Soft-fails per broker if MCP/API is down; GT-only gap fill still runs.

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
# Terminal A — continuous service (scheduler + MCP HTTP)
portfolio serve --mcp-http --host 127.0.0.1 --port 3460

# Terminal B — one-shot smoke (optional)
portfolio jobs list
portfolio jobs run connector_sync --force   # live connectors if configured
portfolio jobs run daily_net_liq --force
portfolio jobs status daily_net_liq
```

Point any MCP client (Grok App, IDE, etc.) at Streamable HTTP `http://127.0.0.1:3460/mcp` (or your gateway URL). Use `jobs_run_tool` then poll `jobs_status_tool(run_id=…)`.

## Tests

Hermetic coverage lives in `tests/test_jobs.py` (shipped runners only):

- sequential multi-account connector sync + lock/`already_running`
- market-day gap fill; no fabricate without GT; reject non-finite/negative
- live exact match + **reprocess today** when last_saved == today
- `run_daily_net_liq` with injected adapters enforces live equality
- CLI `sync` / `jobs` + MCP tools + scheduler registration smoke
