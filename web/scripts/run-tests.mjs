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

const results = [];
let failed = 0;

for (const suite of selected) {
  const script = join(root, suite.file);
  process.stdout.write(`→ ${suite.id}: ${suite.title} ... `);
  const started = Date.now();
  const r = spawnSync(process.execPath, [script], {
    cwd: root,
    encoding: "utf8",
    env: {
      ...process.env,
      COVERAGE_SCRATCH:
        process.env.COVERAGE_SCRATCH ||
        process.env.GOAL_SCRATCH ||
        join(root, "coverage/scratch"),
    },
  });
  const ms = Date.now() - started;
  const ok = r.status === 0;
  if (!ok) failed += 1;
  results.push({ id: suite.id, ok, ms, status: r.status });
  console.log(ok ? `OK (${ms}ms)` : `FAIL (exit ${r.status}, ${ms}ms)`);
  if (r.stdout?.trim()) {
    for (const line of r.stdout.trim().split("\n")) {
      console.log(`  ${line}`);
    }
  }
  if (!ok && r.stderr?.trim()) {
    for (const line of r.stderr.trim().split("\n").slice(0, 40)) {
      console.error(`  ${line}`);
    }
  }
}

console.log("\n--- summary ---");
for (const r of results) {
  console.log(`${r.ok ? "PASS" : "FAIL"}  ${r.id}  ${r.ms}ms`);
}
console.log(
  failed === 0
    ? `\nAll ${results.length} suite(s) passed.\n`
    : `\n${failed}/${results.length} suite(s) failed.\n`,
);
process.exit(failed === 0 ? 0 : 1);
