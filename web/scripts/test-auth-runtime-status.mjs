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
  const prevGrokId = process.env.GROK_AUTH_CLIENT_ID;
  const prevGrokSecret = process.env.GROK_AUTH_CLIENT_SECRET;
  const prevDb = process.env.DATABASE_URL;
  const prevSecret = process.env.BETTER_AUTH_SECRET;
  delete process.env.AUTH_DISABLE_GROK_BROKER;
  delete process.env.GOOGLE_CLIENT_ID;
  delete process.env.GOOGLE_CLIENT_SECRET;
  delete process.env.TWITTER_CLIENT_ID;
  delete process.env.TWITTER_CLIENT_SECRET;
  delete process.env.GROK_AUTH_CLIENT_ID;
  delete process.env.GROK_AUTH_CLIENT_SECRET;

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

  // Bare Vercel without platform injection → broken/unconfigured
  const vercelBare = getAuthRuntimeStatus("my-app.vercel.app");
  assert.equal(vercelBare.hostKind, "published");
  assert.equal(vercelBare.pgliteUsable, false);
  assert.ok(
    vercelBare.mode === "unconfigured" ||
      vercelBare.publishLikelyBroken ||
      vercelBare.mode === "direct_social",
    `vercel bare mode=${vercelBare.mode}`,
  );
  if (!process.env.GOOGLE_CLIENT_ID && !process.env.TWITTER_CLIENT_ID) {
    assert.ok(
      vercelBare.issues.some((i) =>
        /GOOGLE|TWITTER|Social|database|GROK_AUTH|platform/i.test(i),
      ),
      "vercel without credentials should list issues",
    );
  }
  if (hasDatabaseUrl()) {
    assert.equal(vercelBare.database, "neon");
  } else {
    assert.ok(
      vercelBare.publishLikelyBroken ||
        vercelBare.issues.some((i) => /database/i.test(i)),
    );
  }

  // Simulated Grok App publish: Vercel + GROK_AUTH_* + DATABASE_URL + secret
  process.env.GROK_AUTH_CLIENT_ID = "platform-client";
  process.env.GROK_AUTH_CLIENT_SECRET = "platform-secret";
  process.env.DATABASE_URL = "postgres://user:pass@ep-test/neondb";
  process.env.BETTER_AUTH_SECRET = "stable-session-secret-for-tests";
  const grokPublish = getAuthRuntimeStatus("investment-portfolio-analysis.grok.me");
  assert.equal(grokPublish.hostKind, "published");
  assert.equal(grokPublish.mode, "deployed_client");
  assert.equal(grokPublish.database, "neon");
  assert.equal(grokPublish.authEnabled, true);
  assert.equal(
    grokPublish.publishLikelyBroken,
    false,
    "platform-injected grok.me publish must be healthy",
  );
  delete process.env.GROK_AUTH_CLIENT_ID;
  delete process.env.GROK_AUTH_CLIENT_SECRET;
  delete process.env.DATABASE_URL;
  delete process.env.BETTER_AUTH_SECRET;

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
  if (prevGrokId === undefined) delete process.env.GROK_AUTH_CLIENT_ID;
  else process.env.GROK_AUTH_CLIENT_ID = prevGrokId;
  if (prevGrokSecret === undefined) delete process.env.GROK_AUTH_CLIENT_SECRET;
  else process.env.GROK_AUTH_CLIENT_SECRET = prevGrokSecret;
  if (prevDb === undefined) delete process.env.DATABASE_URL;
  else process.env.DATABASE_URL = prevDb;
  if (prevSecret === undefined) delete process.env.BETTER_AUTH_SECRET;
  else process.env.BETTER_AUTH_SECRET = prevSecret;

  console.log("OK auth runtime status tests passed");
  process.exitCode = 0;
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close().catch(() => {});
}
