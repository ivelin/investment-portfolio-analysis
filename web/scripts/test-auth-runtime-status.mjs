#!/usr/bin/env node
import { createServer } from "vite";
import assert from "node:assert/strict";

const vite = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
  root: "/workspace",
});

try {
  const { getAuthRuntimeStatus } = await vite.ssrLoadModule(
    "/src/lib/auth/auth-runtime-status.ts",
  );

  const sandbox = getAuthRuntimeStatus("abc.grok-sandbox.com");
  assert.equal(sandbox.mode, "preview_client");
  assert.equal(sandbox.hostKind, "sandbox");
  assert.equal(sandbox.publishLikelyBroken, false);

  const published = getAuthRuntimeStatus("my-app.grok.me");
  assert.equal(published.hostKind, "published");
  assert.equal(published.mode, "preview_client");
  assert.equal(published.publishLikelyBroken, true);
  assert.ok(published.issues.length >= 1);
  assert.ok(published.hint);

  // Missing DB alone is enough to break publish
  assert.ok(
    published.issues.some((i) => /database/i.test(i)),
    "should flag missing database on published host",
  );

  const local = getAuthRuntimeStatus("localhost");
  assert.equal(local.hostKind, "local");
  assert.equal(local.publishLikelyBroken, false);

  console.log("OK auth runtime status tests passed");
  process.exitCode = 0;
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close().catch(() => {});
}
