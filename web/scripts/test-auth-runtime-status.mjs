#!/usr/bin/env node
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

try {
  const { getAuthRuntimeStatus, pgliteUsableInThisRuntime } =
    await vite.ssrLoadModule("/src/lib/auth/auth-runtime-status.ts");
  const { hasDatabaseUrl } = await vite.ssrLoadModule("/src/lib/db-url.ts");

  assert.equal(pgliteUsableInThisRuntime(), true, "sandbox runtime must allow PGLite");

  const prevDisable = process.env.AUTH_DISABLE_GROK_BROKER;
  const prevG = process.env.GOOGLE_CLIENT_ID;
  const prevGs = process.env.GOOGLE_CLIENT_SECRET;
  const prevT = process.env.TWITTER_CLIENT_ID;
  const prevTs = process.env.TWITTER_CLIENT_SECRET;
  delete process.env.AUTH_DISABLE_GROK_BROKER;
  delete process.env.GOOGLE_CLIENT_ID;
  delete process.env.GOOGLE_CLIENT_SECRET;
  delete process.env.TWITTER_CLIENT_ID;
  delete process.env.TWITTER_CLIENT_SECRET;

  const sandbox = getAuthRuntimeStatus("abc.grok-sandbox.com");
  assert.ok(
    sandbox.mode === "preview_client" || sandbox.mode === "direct_social",
    `sandbox mode=${sandbox.mode}`,
  );
  assert.equal(sandbox.hostKind, "sandbox");
  assert.equal(sandbox.publishLikelyBroken, false);
  assert.equal(sandbox.pgliteUsable, true);
  assert.equal(sandbox.authEnabled, true);

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

  const prevVercel = process.env.VERCEL;
  const prevVercelEnv = process.env.VERCEL_ENV;
  process.env.VERCEL = "1";
  process.env.VERCEL_ENV = "production";
  assert.equal(pgliteUsableInThisRuntime(), false, "VERCEL=1 must disable PGLite");
  const vercelPublished = getAuthRuntimeStatus("my-app.vercel.app");
  assert.equal(vercelPublished.hostKind, "published");
  assert.equal(vercelPublished.pgliteUsable, false);
  assert.ok(
    vercelPublished.mode === "unconfigured" ||
      vercelPublished.publishLikelyBroken ||
      vercelPublished.mode === "direct_social",
    `vercel mode=${vercelPublished.mode}`,
  );
  if (!process.env.GOOGLE_CLIENT_ID && !process.env.TWITTER_CLIENT_ID) {
    assert.ok(
      vercelPublished.issues.some((i) => /GOOGLE|TWITTER|Social|database/i.test(i)),
      "vercel without social env should list issues",
    );
  }
  if (hasDatabaseUrl()) {
    assert.equal(vercelPublished.database, "neon");
  } else {
    assert.ok(
      vercelPublished.publishLikelyBroken ||
        vercelPublished.issues.some((i) => /database/i.test(i)),
    );
  }
  if (prevVercel === undefined) delete process.env.VERCEL;
  else process.env.VERCEL = prevVercel;
  if (prevVercelEnv === undefined) delete process.env.VERCEL_ENV;
  else process.env.VERCEL_ENV = prevVercelEnv;

  const local = getAuthRuntimeStatus("localhost");
  assert.equal(local.hostKind, "local");
  assert.equal(local.publishLikelyBroken, false);
  assert.ok(
    local.mode === "preview_client" || local.mode === "direct_social",
    `local mode=${local.mode}`,
  );

  if (prevDisable === undefined) delete process.env.AUTH_DISABLE_GROK_BROKER;
  else process.env.AUTH_DISABLE_GROK_BROKER = prevDisable;
  if (prevG === undefined) delete process.env.GOOGLE_CLIENT_ID;
  else process.env.GOOGLE_CLIENT_ID = prevG;
  if (prevGs === undefined) delete process.env.GOOGLE_CLIENT_SECRET;
  else process.env.GOOGLE_CLIENT_SECRET = prevGs;
  if (prevT === undefined) delete process.env.TWITTER_CLIENT_ID;
  else process.env.TWITTER_CLIENT_ID = prevT;
  if (prevTs === undefined) delete process.env.TWITTER_CLIENT_SECRET;
  else process.env.TWITTER_CLIENT_SECRET = prevTs;

  console.log("OK auth runtime status tests passed");
  process.exitCode = 0;
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close().catch(() => {});
}
