#!/usr/bin/env node
import { createServer } from "vite";
import assert from "node:assert/strict";

const vite = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
  root: "/workspace",
});

try {
  const { getAuthRuntimeStatus, pgliteUsableInThisRuntime } =
    await vite.ssrLoadModule("/src/lib/auth/auth-runtime-status.ts");
  const { hasDatabaseUrl } = await vite.ssrLoadModule("/src/lib/db-url.ts");

  assert.equal(pgliteUsableInThisRuntime(), true, "sandbox runtime must allow PGLite");

  const sandbox = getAuthRuntimeStatus("abc.grok-sandbox.com");
  assert.equal(sandbox.mode, "preview_client");
  assert.equal(sandbox.hostKind, "sandbox");
  assert.equal(sandbox.publishLikelyBroken, false);
  assert.equal(sandbox.pgliteUsable, true);

  // Live preview often forwards the *published* hostname while still running
  // the sandbox process. That must NOT look like a broken production deploy.
  const publishedHostInSandbox = getAuthRuntimeStatus(
    "investment-portfolio-analysis.grok.me",
  );
  assert.equal(publishedHostInSandbox.hostKind, "published");
  assert.equal(publishedHostInSandbox.pgliteUsable, true);
  assert.equal(
    publishedHostInSandbox.publishLikelyBroken,
    false,
    "sandbox process with *.grok.me Host must not block login",
  );
  assert.equal(publishedHostInSandbox.issues.length, 0);

  // Simulate real Vercel serverless: PGLite unusable
  const prevVercel = process.env.VERCEL;
  const prevVercelEnv = process.env.VERCEL_ENV;
  process.env.VERCEL = "1";
  process.env.VERCEL_ENV = "production";
  assert.equal(pgliteUsableInThisRuntime(), false, "VERCEL=1 must disable PGLite");
  const vercelPublished = getAuthRuntimeStatus("my-app.grok.me");
  assert.equal(vercelPublished.hostKind, "published");
  assert.equal(vercelPublished.pgliteUsable, false);
  if (hasDatabaseUrl()) {
    // Sandbox may carry a gitignored Neon bootstrap — DB is then OK.
    assert.equal(vercelPublished.database, "neon");
    assert.ok(!vercelPublished.issues.some((i) => /database/i.test(i)));
  } else {
    assert.equal(vercelPublished.publishLikelyBroken, true);
    assert.ok(vercelPublished.issues.some((i) => /database/i.test(i)));
  }
  if (prevVercel === undefined) delete process.env.VERCEL;
  else process.env.VERCEL = prevVercel;
  if (prevVercelEnv === undefined) delete process.env.VERCEL_ENV;
  else process.env.VERCEL_ENV = prevVercelEnv;

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
