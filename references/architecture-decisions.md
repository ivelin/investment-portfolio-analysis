# Portfolio Analysis Architecture Decisions (2026-05)

## Data Ingestion Strategy
- **Primary source**: Schwab exported CSV/XML files (Transactions, Realized Gain/Loss, Positions)
- **Reason**: Live Schwab API + MCP proved too flaky and unreliable for daily/weekly use
- **Database**: SQLite (for consistency with the `stock-analysis` skill)
- **Future option**: DuckDB can be used as an analytical query layer on top of the SQLite files

## Development Workflow
- All new work happens in the dedicated repository: `ivelin/investment-portfolio-analysis`
- Feature development, tests, and debugging are delegated via **grok-build**
- The skill in `~/.hermes/skills/` is symlinked to the repo for zero duplication

## Core Analytical Workflows
- "Weed the Garden" capital efficiency scan (inspired by ThinkScript logic)
- Time-weighted performance metrics
- CANSLIM adherence review of historical trades
- Cross-referencing with `stock-analysis` market data

## When to Revisit API Approach
Only reconsider live API/MCP if:
- Schwab significantly improves OAuth reliability, or
- A stable, well-maintained open source MCP server matures (e.g. jkoelker/schwab-mcp)

## CLI as the Primary Extension Point for Tools & Workflows (2026-05)

- **Decision**: All new tools, workflows, and operational features added to the skill must be implemented as subcommands under the `portfolio` CLI.
- **Rationale**:
  - Provides a single, consistent, and discoverable interface (`portfolio --help`).
  - Keeps the skill cleanly packaged as a proper Python application.
  - Avoids fragmentation from scattered standalone scripts.
  - Improves long-term maintainability and agent usability.
- **Implementation Rule**:
  - New functionality is added by extending `portfolio_analysis/cli.py` (or a dedicated commands structure under it).
  - Direct scripts under `tools/` are now considered legacy or internal utilities.
- **Migration Direction**:
  - Existing high-value tools in `tools/` will be progressively converted into CLI subcommands.
  - Direct execution of tools (`python tools/xxx.py`) is deprecated for normal use.
- **Documentation**:
  - `SKILL.md` is the primary place where recommended workflows are described and will be updated to reflect the `portfolio` CLI as the default interface.

This decision establishes a clear architectural direction for the evolution of the skill.

This document captures the deliberate architectural choices made after evaluating live API vs file-based approaches.

## Multi-tenant hosted platform (2026-07)

- **Decision**: Hosted product on grok.me is **multi-tenant** with Neon Postgres,
  Better Auth (Grok broker), REST + MCP APIs, and a full-stack web dashboard.
  Local skill mode (SQLite under `PORTFOLIO_ANALYSIS_HOME`) remains fully supported.
- **Branch**: `feature/multi-tenant-platform`
- **Canonical docs**: [docs/MULTI_TENANT_ARCHITECTURE.md](../docs/MULTI_TENANT_ARCHITECTURE.md),
  [docs/MULTI_TENANT_SECURITY.md](../docs/MULTI_TENANT_SECURITY.md)
- **Hard rules**:
  - Public repo must never contain real balances, tokens, exports, or PII.
  - Every hosted portfolio row is scoped by `tenant_id` + membership check.
  - Demo/synthetic data only until a tenant connects their own sources.
  - Connector secrets are encrypted at rest and never returned by APIs.
- **Rationale**: Local MCP is single-operator; hosting requires auth, isolation,
  and a scalable DB while preserving ground-truth integrity philosophy.
