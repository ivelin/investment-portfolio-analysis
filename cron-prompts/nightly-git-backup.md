# Nightly Git Backup — portfolio-analysis

Run the nightly backup for the portfolio-analysis repository.

## Instructions
1. `cd` to the portfolio-analysis repository root (this project’s workspace).
2. `git add -A`
3. If there are staged changes, commit with message `nightly backup: $(date '+%Y-%m-%d %H:%M')`
4. Always push to `origin/main`
5. Log under `${TMPDIR:-/tmp}/portfolio-analysis-git-push-*.log`

Prefer the scripted path: `tools/nightly-git-backup.sh` (resolves the repo root from its own location).

## Delivery Rule
- On success with no changes or successful push → reply exactly `HEARTBEAT_OK`
- On any failure (commit or push error) → deliver full error + log content to the operator’s configured chat

## Public-repo caution
Never stage personal Schwab exports, `~/.investment-portfolio-analysis/` data, tokens, or `.env` files. Those paths are gitignored and must stay local.
