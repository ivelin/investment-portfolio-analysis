#!/usr/bin/env node
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

try {
  const { getAuthRuntimeStatus, pgliteUsableInThisRuntime } =
    await vite.ssrLoadModule("/src/lib/auth/auth-runtime-status.ts");
  const { hasDatabaseUrl } = await vite.ssrLoadModule("/src/lib/db-url.ts");

  assert.equal(pgliteUsableInThisRuntime(), true, "sandbox runtime must allow PGLite");

  const sandbox = getAuthRuntimeStatus("abc.grok-sandbox.com");
  // Local/sandbox without VERCEL + without GOOGLE_*: Grok broker preview path
  assert.ok(
    sandbox.mode === "preview_client" || sandbox.mode === "direct_social",
    `sandbox mode=${sandbox.mode}`,
  );
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
  const vercelPublished = getAuthRuntimeStatus("my-app.vercel.app");
  assert.equal(vercelPublished.hostKind, "published");
  assert.equal(vercelPublished.pgliteUsable, false);
  // Vercel without GOOGLE_*/TWITTER_* must not look like healthy Grok preview auth
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

  console.log("OK auth runtime status tests passed");
  process.exitCode = 0;
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close().catch(() => {});
}
