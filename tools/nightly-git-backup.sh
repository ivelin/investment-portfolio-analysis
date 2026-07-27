#!/bin/bash
set -euo pipefail

# Nightly git backup for portfolio-analysis skill
# Location: tools/nightly-git-backup.sh (inside the skill repo)

# Resolve repo root from this script's location (portable; no hard-coded home path).
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${TMPDIR:-/tmp}/portfolio-analysis-git-push-$(date +%Y%m%d-%H%M).log"

cd "$REPO_DIR"

{
  echo "=== Nightly auto-commit + push for portfolio-analysis at $(date) ==="
  git status --porcelain

  git add -A

  if git diff --cached --quiet; then
    echo "No changes to commit."
  else
    git commit -m "nightly backup: $(date '+%Y-%m-%d %H:%M')"
    echo "Committed changes."
  fi

  echo "Pushing to origin/main..."
  git push origin main

  echo "✅ Nightly commit + push completed successfully"
} > "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  echo "🚨 Nightly portfolio-analysis backup FAILED (exit $EXIT_CODE)"
  cat "$LOG_FILE"
  exit $EXIT_CODE
fi

# Silent success
exit 0
