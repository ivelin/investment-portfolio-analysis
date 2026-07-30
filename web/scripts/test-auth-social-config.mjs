#!/usr/bin/env node
/**
 * Unit tests for social-config + oauth redirect fixes.
 * Proves: Vercel never falls to Grok; non-Vercel uses broker; relative redirect_uri fixed.
 */
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

try {
  const cfg = await vite.ssrLoadModule("/src/lib/auth/social-config.ts");
  const redirect = await vite.ssrLoadModule("/src/lib/auth/oauth-redirect.ts");
  const { SOCIAL_PROVIDERS } = await vite.ssrLoadModule(
    "/src/lib/auth/providers.ts",
  );

  assert.equal(SOCIAL_PROVIDERS.length, 2);
  assert.deepEqual(
    SOCIAL_PROVIDERS.map((p) => p.providerId),
    ["google", "twitter"],
  );

  // Vercel without social env → unconfigured (NOT grok_broker)
  assert.equal(
    cfg.resolveAuthBackendMode({ VERCEL: "1", VITE_AUTH_ENABLED: "true" }),
    "unconfigured",
  );
  assert.equal(cfg.isAuthConfigured({ VERCEL: "1" }), false);

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

  // Non-Vercel without direct → grok_broker (sandbox/CLI default)
  assert.equal(cfg.resolveAuthBackendMode({}), "grok_broker");
  assert.equal(cfg.isAuthConfigured({}), true);

  // Opt-out
  assert.equal(
    cfg.resolveAuthBackendMode({ AUTH_DISABLE_GROK_BROKER: "true" }),
    "unconfigured",
  );

  // Vercel never grok even with allow-style flags
  assert.equal(
    cfg.resolveAuthBackendMode({
      VERCEL: "1",
      AUTH_DISABLE_GROK_BROKER: "false",
    }),
    "unconfigured",
  );

  // Direct social wins over broker
  assert.equal(
    cfg.resolveAuthBackendMode({
      GOOGLE_CLIENT_ID: "g",
      GOOGLE_CLIENT_SECRET: "s",
      GROK_AUTH_CLIENT_ID: "broker",
      GROK_AUTH_CLIENT_SECRET: "broker-secret",
    }),
    "direct_social",
  );

  assert.equal(cfg.GROK_BROKER_HOST, "auth.grok.me");
  assert.ok(!cfg.DIRECT_SOCIAL_AUTHORIZE_HOSTS.includes("auth.grok.me"));

  // ── redirect_uri absolute fix (the Invalid redirect URI bug) ──
  assert.equal(
    redirect.absolutizeOAuthRedirectUri(
      "/oauth2/callback/twitter",
      "https://abc.grok-sandbox.com",
    ),
    "https://abc.grok-sandbox.com/api/auth/oauth2/callback/twitter",
  );
  assert.equal(
    redirect.absolutizeOAuthRedirectUri(
      "/api/auth/oauth2/callback/google",
      "https://abc.grok-sandbox.com",
    ),
    "https://abc.grok-sandbox.com/api/auth/oauth2/callback/google",
  );
  assert.equal(
    redirect.absolutizeOAuthRedirectUri(
      "https://abc.grok-sandbox.com/api/auth/oauth2/callback/twitter",
      "https://other.example.com",
    ),
    "https://abc.grok-sandbox.com/api/auth/oauth2/callback/twitter",
  );

  const broken =
    "https://auth.grok.me/api/auth/oauth2/authorize?response_type=code&client_id=grok_preview&redirect_uri=%2Foauth2%2Fcallback%2Ftwitter&state=x&scope=openid";
  const fixed = redirect.fixOAuthAuthorizeUrl(
    broken,
    "https://abc.grok-sandbox.com",
  );
  const fixedUri = new URL(fixed).searchParams.get("redirect_uri");
  assert.equal(
    fixedUri,
    "https://abc.grok-sandbox.com/api/auth/oauth2/callback/twitter",
    "relative redirect_uri must become absolute under app origin",
  );

  // Client must keep social → oauth2 fallthrough for broker
  const { readFileSync } = await import("node:fs");
  const { join, dirname } = await import("node:path");
  const { fileURLToPath } = await import("node:url");
  const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
  const clientSrc = readFileSync(
    join(webRoot, "src/lib/auth/client.ts"),
    "utf8",
  );
  assert.match(clientSrc, /signIn\.social/);
  assert.match(clientSrc, /signIn\.oauth2/);
  assert.match(clientSrc, /genericOAuthClient/);
  assert.match(clientSrc, /fixOAuthAuthorizeUrl/);

  const popupSrc = readFileSync(
    join(webRoot, "src/lib/auth/popup.server.ts"),
    "utf8",
  );
  assert.match(popupSrc, /signInSocial|signInWithOAuth2/);
  assert.match(popupSrc, /fixOAuthAuthorizeUrl/);
  assert.match(popupSrc, /if\s*\(\s*social\.ok\s*\)/);

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
