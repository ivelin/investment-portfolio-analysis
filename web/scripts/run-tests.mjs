#!/usr/bin/env node
/**
 * Unified multi-tenant test runner (unit + api + mcp + e2e).
 * Exit 0 only when every selected suite passes.
 */
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

/** MECE packs — pure/unit first, then API, MCP, E2E last. */
const SUITES = [
  { id: "mece", file: "scripts/test-mece-decisions.mjs", title: "MECE decision matrices" },
  {
    id: "auth-status",
    file: "scripts/test-auth-runtime-status.mjs",
    title: "Auth runtime status",
  },
  {
    id: "auth-social",
    file: "scripts/test-auth-social-config.mjs",
    title: "Auth social config (Google/X, no Grok on Vercel)",
  },
  {
    id: "oauth-bind",
    file: "scripts/test-oauth-bind-compliance.mjs",
    title: "OAuth session bind + intended use",
  },
  {
    id: "legal",
    file: "scripts/test-legal-acceptance.mjs",
    title: "Legal acceptance pack",
  },
  {
    id: "isolation",
    file: "scripts/test-tenant-isolation.mjs",
    title: "Tenant isolation",
  },
  {
    id: "token-refresh",
    file: "scripts/test-token-refresh.mjs",
    title: "Tenant-scoped token refresh",
  },
  {
    id: "broker-setup",
    file: "scripts/test-broker-setup.mjs",
    title: "Broker connector setup path",
  },
  {
    id: "broker-readonly",
    file: "scripts/test-broker-read-only.mjs",
    title: "Broker connectors read-only (no orders)",
  },
  {
    id: "broker-sync",
    file: "scripts/test-broker-sync.mjs",
    title: "Broker sync pull/ingest + isolation",
  },
  {
    id: "oauth-callback",
    file: "scripts/test-oauth-callback.mjs",
    title: "OAuth callback bind edges",
  },
  {
    id: "db-isolation",
    file: "scripts/test-db-isolation.mjs",
    title: "Preview DB isolation from publish Neon",
  },
  {
    id: "dashboard-switch",
    file: "scripts/test-dashboard-live-switch.mjs",
    title: "Dashboard demo → live Schwab switch",
  },
  {
    id: "api",
    file: "tests/api/critical-path.mjs",
    title: "API critical path (summary/health/jobs)",
  },
  {
    id: "mcp",
    file: "tests/mcp/critical-path.mjs",
    title: "MCP critical path (catalog + tools)",
  },
  {
    id: "e2e",
    file: "tests/e2e/entry-smoke.mjs",
    title: "E2E entry (home + login)",
  },
];

const only = process.argv.slice(2).filter((a) => !a.startsWith("-"));
const skipE2e = process.env.SKIP_E2E === "1";
let selected =
  only.length === 0
    ? SUITES
    : SUITES.filter((s) => only.includes(s.id) || only.includes(s.file));

if (skipE2e) {
  selected = selected.filter((s) => s.id !== "e2e");
}

if (selected.length === 0) {
  console.error(
    "No matching suites. Known ids:",
    SUITES.map((s) => s.id).join(", "),
  );
  process.exit(2);
}

console.log(`\nweb test suite — ${selected.length} suite(s)\n`);

let failed = 0;
for (const suite of selected) {
  process.stdout.write(`→ ${suite.id}: ${suite.title} ... `);
  const started = Date.now();
  const r = spawnSync(process.execPath, [join(root, suite.file)], {
    cwd: root,
    env: { ...process.env, GROK_AGENT: "1" },
    encoding: "utf8",
  });
  const ms = Date.now() - started;
  if (r.status === 0) {
    console.log(`OK (${ms}ms)`);
    if (r.stdout?.trim()) {
      for (const line of r.stdout.trim().split("\n")) {
        console.log(`  ${line}`);
      }
    }
  } else {
    failed += 1;
    console.log(`FAIL (${ms}ms)`);
    if (r.stdout) console.log(r.stdout);
    if (r.stderr) console.error(r.stderr);
  }
}

console.log("\n--- summary ---");
if (failed) {
  console.error(`${failed} suite(s) failed`);
  process.exit(1);
}
console.log(`All ${selected.length} suite(s) passed.\n`);
