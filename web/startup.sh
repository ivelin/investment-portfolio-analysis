#!/bin/sh
set -eu
cd /workspace

# Preview is always isolated PGLite. Never inject the publish Neon URL into
# the dev server (prod data must not be used for local/preview testing).
unset DATABASE_URL POSTGRES_URL POSTGRES_PRISMA_URL POSTGRES_URL_NON_POOLING NEON_DATABASE_URL 2>/dev/null || true
rm -f .env.local 2>/dev/null || true

# Persist preview PGLite on disk so agent tooling + dev server share state.
# Tests do NOT set this — they use in-memory PGLite.
export GROK_PREVIEW_PERSIST=1
export GROK_AGENT="${GROK_AGENT:-1}"

if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
  exit 0
fi
npm run dev >>/tmp/app-startup.log 2>&1 &
