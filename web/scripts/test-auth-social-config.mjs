#!/usr/bin/env node
/**
 * Unit tests for shipped social-config selection (no network, no DB).
 * Proves Vercel never falls through to Grok broker / auth.grok.me.
 */
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

try {
  const cfg = await vite.ssrLoadModule("/src/lib/auth/social-config.ts");
  const { SOCIAL_PROVIDERS } = await vite.ssrLoadModule(
    "/src/lib/auth/providers.ts",
  );

  // Catalog: Google + X only
  assert.equal(SOCIAL_PROVIDERS.length, 2);
  assert.deepEqual(
    SOCIAL_PROVIDERS.map((p) => p.providerId),
    ["google", "twitter"],
  );
  assert.deepEqual(
    SOCIAL_PROVIDERS.map((p) => p.label),
    ["Google", "X"],
  );

  // Vercel without social env → unconfigured (NOT grok_broker)
  assert.equal(
    cfg.resolveAuthBackendMode({ VERCEL: "1", VITE_AUTH_ENABLED: "true" }),
    "unconfigured",
  );
  assert.equal(
    cfg.isAuthConfigured({ VERCEL: "1" }),
    false,
    "Vercel without GOOGLE/TWITTER must not use Grok preview client",
  );

  // Direct social on Vercel
  const vercelSocial = {
    VERCEL: "1",
    GOOGLE_CLIENT_ID: "g-id",
    GOOGLE_CLIENT_SECRET: "g-secret",
    TWITTER_CLIENT_ID: "t-id",
    TWITTER_CLIENT_SECRET: "t-secret",
  };
  assert.equal(cfg.resolveAuthBackendMode(vercelSocial), "direct_social");
  assert.equal(cfg.isAuthConfigured(vercelSocial), true);
  const social = cfg.buildSocialProvidersFromEnv(vercelSocial);
  assert.ok(social.google?.clientId === "g-id");
  assert.ok(social.twitter?.clientId === "t-id");
  // Secrets exist in object but tests only check presence of keys — never log values
  assert.ok(social.google?.clientSecret);
  assert.ok(social.twitter?.clientSecret);

  // Vercel + only Google
  assert.deepEqual(
    cfg.enabledDirectProviderIds({
      VERCEL: "1",
      GOOGLE_CLIENT_ID: "g",
      GOOGLE_CLIENT_SECRET: "s",
    }),
    ["google"],
  );

  // Non-Vercel without direct → grok_broker (sandbox/local)
  assert.equal(cfg.resolveAuthBackendMode({}), "grok_broker");
  assert.equal(cfg.isAuthConfigured({}), true);

  // Disabled
  assert.equal(
    cfg.resolveAuthBackendMode({ VITE_AUTH_ENABLED: "false" }),
    "disabled",
  );

  // Direct social wins over Grok even with GROK_AUTH_* present
  assert.equal(
    cfg.resolveAuthBackendMode({
      GOOGLE_CLIENT_ID: "g",
      GOOGLE_CLIENT_SECRET: "s",
      GROK_AUTH_CLIENT_ID: "broker",
      GROK_AUTH_CLIENT_SECRET: "broker-secret",
      VERCEL: "1",
    }),
    "direct_social",
  );

  // Authorize hosts for direct social do not include Grok broker
  assert.ok(
    !cfg.DIRECT_SOCIAL_AUTHORIZE_HOSTS.includes("auth.grok.me"),
  );
  assert.equal(cfg.GROK_BROKER_HOST, "auth.grok.me");

  // Runtime status on Vercel without social marks unconfigured / issues
  const prevV = process.env.VERCEL;
  const prevG = process.env.GOOGLE_CLIENT_ID;
  delete process.env.GOOGLE_CLIENT_ID;
  delete process.env.GOOGLE_CLIENT_SECRET;
  delete process.env.TWITTER_CLIENT_ID;
  delete process.env.TWITTER_CLIENT_SECRET;
  process.env.VERCEL = "1";
  process.env.VERCEL_ENV = "preview";
  const { getAuthRuntimeStatus } = await vite.ssrLoadModule(
    "/src/lib/auth/auth-runtime-status.ts",
  );
  const st = getAuthRuntimeStatus("my-app.vercel.app");
  assert.equal(st.hostKind, "published");
  assert.ok(
    st.mode === "unconfigured" || st.publishLikelyBroken,
    "Vercel without social env should surface config issues",
  );
  assert.ok(
    st.issues.some((i) => /GOOGLE|TWITTER|Social/i.test(i)),
    "issues mention social env",
  );
  if (prevV === undefined) delete process.env.VERCEL;
  else process.env.VERCEL = prevV;
  delete process.env.VERCEL_ENV;
  if (prevG !== undefined) process.env.GOOGLE_CLIENT_ID = prevG;

  // Regression: client sign-in must fall through to oauth2 on social error
  // (grok_broker has empty socialProviders). Throwing before oauth2 is a bug.
  const { readFileSync } = await import("node:fs");
  const { join, dirname } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
  const clientSrc = readFileSync(
    join(webRoot, "src/lib/auth/client.ts"),
    "utf8",
  );
  assert.match(
    clientSrc,
    /if\s*\(\s*!social\.error\s*\)/,
    "client must succeed-only on social, not throw-then-oauth2",
  );
  const socialCall = clientSrc.indexOf("authClient.signIn.social");
  const oauth2Call = clientSrc.indexOf("authClient.signIn.oauth2");
  const throwBeforeOauth2 = clientSrc
    .slice(socialCall, oauth2Call)
    .includes("throw new Error");
  assert.equal(
    throwBeforeOauth2,
    false,
    "client must not throw between social and oauth2 (blocks broker fallback)",
  );
  assert.ok(oauth2Call > socialCall, "oauth2 must follow social attempt");

  // Regression: popup must use social only when Response.ok — Response objects
  // are always truthy so `social ?? oauth2` never falls through.
  const popupSrc = readFileSync(
    join(webRoot, "src/lib/auth/popup.server.ts"),
    "utf8",
  );
  assert.match(
    popupSrc,
    /if\s*\(\s*social\.ok\s*\)/,
    "popup must gate social on Response.ok before accepting it",
  );
  assert.match(
    popupSrc,
    /signInWithOAuth2/,
    "popup must retain oauth2 fallback for grok_broker",
  );
  assert.equal(
    /social\s*\?\?\s*[\s\S]*signInWithOAuth2/.test(popupSrc),
    false,
    "popup must not use truthy Response ?? fallback (broken on !ok)",
  );

  // Email/password stays off
  const { emailAndPasswordEnabled } = await vite.ssrLoadModule(
    "/src/lib/auth/email-password.ts",
  );
  assert.equal(emailAndPasswordEnabled, false);

  console.log("OK auth social-config tests passed");
  process.exitCode = 0;
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close().catch(() => {});
}
