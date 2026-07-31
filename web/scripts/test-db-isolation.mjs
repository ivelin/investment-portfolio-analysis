#!/usr/bin/env node
/**
 * Hard isolation: preview must never resolve publish Neon bootstrap URL.
 */
import assert from "node:assert/strict";
import { createViteTestServer } from "./vite-test-server.mjs";
import { readFileSync, existsSync } from "node:fs";

const vite = await createViteTestServer();

try {
  const dbUrl = await vite.ssrLoadModule("/src/lib/db-url.ts");
  const runtime = await vite.ssrLoadModule("/src/lib/runtime-env.ts");

  assert.equal(runtime.pgliteUsableInThisRuntime(), true, "agent is pglite runtime");

  let bootstrap = null;
  if (existsSync("src/lib/db-bootstrap.secret.ts")) {
    const t = readFileSync("src/lib/db-bootstrap.secret.ts", "utf8");
    const m = t.match(/["'](postgres(?:ql)?:\/\/[^"']+)["']/);
    bootstrap = m?.[1] ?? null;
  }

  if (bootstrap) {
    assert.equal(dbUrl.isPublishBootstrapUrl(bootstrap), true);
    const prev = process.env.DATABASE_URL;
    process.env.DATABASE_URL = bootstrap;
    try {
      assert.equal(
        dbUrl.resolveDatabaseUrl(),
        undefined,
        "preview must ignore publish bootstrap DATABASE_URL",
      );
    } finally {
      if (prev === undefined) delete process.env.DATABASE_URL;
      else process.env.DATABASE_URL = prev;
    }
  }

  // Without env, always undefined in preview
  const cleared = process.env.DATABASE_URL;
  delete process.env.DATABASE_URL;
  try {
    assert.equal(dbUrl.resolveDatabaseUrl(), undefined);
  } finally {
    if (cleared !== undefined) process.env.DATABASE_URL = cleared;
  }

  const presence = dbUrl.databaseEnvPresence();
  assert.ok("bootstrap" in presence);
  assert.ok("DATABASE_URL" in presence);

  console.log("OK db isolation guards");
} finally {
  await vite.close();
}
