# Security and privacy

This project is designed so **personal brokerage data stays on the operator’s machine**, in a **canonical directory outside the source repository**.

## Canonical instance home (required convention)

All concrete *instance* data for a running operator lives under:

```text
~/.investment-portfolio-analysis/                 # PORTFOLIO_ANALYSIS_HOME
  portfolio.db                         # SQLite ground truth + derived tables
  exports/                             # multi-broker raw exports (preferred)
    schwab/                            # Charles Schwab / TDA structured exports
    ibkr/                              # Interactive Brokers (when used)
    robinhood/
    fidelity/
  schwab-exports/                      # legacy flat Schwab tree (still supported)
  reports/                             # PDFs, charts, text reports (may show balances)
  tokens/
    schwab.json                        # preferred OAuth token path
  connectors/                          # non-secret connector config (mode, MCP URL)
    schwab.json
  secrets/                             # OAuth client secrets + pending PKCE (0600/0700)
    schwab_oauth.json
  schwab/tokens.json                   # older Schwab token path (still read)
  .env                                 # optional market-data / broker keys for this skill
  cache/                               # optional local caches
  locks/                               # advisory flock files per job (no secrets)
  jobs/                                # job status JSON (counts/dates only; no secrets)
    runs/                              # per run_id status for MCP poll
```

| Path | Env override |
|------|----------------|
| Instance root | `PORTFOLIO_ANALYSIS_HOME` |
| SQLite DB | `PORTFOLIO_ANALYSIS_DB_PATH` |
| Exports root | `PORTFOLIO_ANALYSIS_EXPORTS_DIR` |
| Reports dir | `PORTFOLIO_ANALYSIS_REPORTS_DIR` |
| Schwab tokens | `SCHWAB_TOKENS_PATH` |

### Connectors (local MCP / remote MCP / direct OAuth)

Live broker feeds are configured **outside the repo** and managed via:

- CLI: `portfolio connectors list|show|set|test|oauth-start|oauth-complete`
- MCP tools: `list_connectors_tool`, `configure_connector_tool`, `test_connector_tool`,
  `connector_oauth_start_tool`, `connector_oauth_complete_tool`, `connector_oauth_status_tool`

Modes: `mcp` (e.g. `http://127.0.0.1:3473/mcp` or a remote gateway URL), `direct`
(Schwab Developer API after OAuth), `exports_only`, `auto`.

Client id/secret and tokens are written only under `secrets/` and `tokens/` with
restrictive permissions. Tool responses are always redacted.

Continuous jobs (`portfolio serve` / `jobs_*` MCP tools) persist **non-secret**
status under `jobs/` and `locks/`. Never put tokens or account numbers in those
files (enforced by status redaction helpers).

Per-broker export directories: `portfolio_analysis.paths.broker_exports_dir("schwab")` etc.
Adapter registry: `portfolio_analysis.brokers` (`portfolio brokers list`).

Implementation: `paths.py`, `connectors/`, and `brokers/` are the SSOT. Do not
introduce new hard-coded `~/...` instance paths—import helpers from
`portfolio_analysis.paths`.

**Never** write personal exports, DB files, tokens, or balance-bearing reports into the git worktree.

Legacy fallbacks (read-only compatibility):

- Exports: if only `schwab-exports/` exists, it is treated as the Schwab tree
- OAuth: `~/.schwab/tokens.json` if present and newer preferred paths do not
- API keys: `~/.env` and `~/.hermes/.env` after the instance-local `.env`

## Never commit

- Anything under `PORTFOLIO_ANALYSIS_HOME` / `~/.investment-portfolio-analysis/`
- Broker export files (CSV, XML, PDF statements, 1099s) from any broker
- Local SQLite databases
- OAuth tokens (`tokens.json`, `client_secret*.json`)
- Environment files with API keys (`.env`, `POLYGON_API_KEY`, `SCHWAB_CLIENT_SECRET`, etc.)
- Unredacted account numbers, taxpayer names, addresses, or SSN/TIN fragments

`.gitignore` blocks the common patterns. Do not use `git add -f` on those paths.

## Safe fixtures

Tracked files under `tests/fixtures/extractions/` are **synthetic**:

- Placeholder account `999-000001`
- Tiny demo holdings (not a real portfolio)
- Redacted recipient identity on the sample 1099-R

They exist only so offline CI can exercise schema and parsers without private data.

## Credentials

Broker and market-data credentials are loaded from the environment (or the
instance-local `.env`). The code never hard-codes API keys or client secrets.

## Reporting a leak

If you believe credentials or personal financial data were committed, rotate the
affected secrets immediately and open an issue (or contact the maintainer)
describing the path and commit. History rewrite + force-push may be required.
