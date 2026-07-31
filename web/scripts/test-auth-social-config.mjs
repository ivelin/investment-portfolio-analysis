/**
 * Unit tests for social-config + oauth redirect fixes.
 *
 * Proves: Vercel uses Grok broker when GROK_AUTH_* present (*.grok.me);
 * works on Vercel (*.grok.me); non-Vercel uses broker; relative redirect_uri fixed.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createViteTestServer } from "./vite-test-server.mjs";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

const vite = await createViteTestServer();
try {
  const social = await vite.ssrLoadModule("/src/lib/auth/social-config.ts");
  const redirect = await vite.ssrLoadModule("/src/lib/auth/oauth-redirect.ts");

  // ── bare Vercel without platform client → unconfigured ──
  assert.equal(
    social.resolveAuthBackendMode({ VERCEL: "1" }),
    "unconfigured",
  );

  // ── Vercel + platform Grok client (*.grok.me publish) → grok_broker ──
  assert.equal(
    social.resolveAuthBackendMode({
      VERCEL: "1",
      GROK_AUTH_CLIENT_ID: "grok_app",
      GROK_AUTH_CLIENT_SECRET: "secret",
    }),
    "grok_broker",
  );

  // ── direct social wins when GOOGLE_* present ──
  assert.equal(
    social.resolveAuthBackendMode({
      VERCEL: "1",
      GOOGLE_CLIENT_ID: "g",
      GOOGLE_CLIENT_SECRET: "gs",
      GROK_AUTH_CLIENT_ID: "grok_app",
      GROK_AUTH_CLIENT_SECRET: "secret",
    }),
    "direct_social",
  );

  // ── sandbox / non-Vercel → grok_broker (preview client) ──
  assert.equal(social.resolveAuthBackendMode({}), "grok_broker");
  assert.equal(
    social.resolveAuthBackendMode({ GROK_AGENT: "1" }),
    "grok_broker",
  );

  // ── opt-out ──
  assert.equal(
    social.resolveAuthBackendMode({
      AUTH_DISABLE_GROK_BROKER: "true",
    }),
    "unconfigured",
  );

  // ── disabled ──
  assert.equal(
    social.resolveAuthBackendMode({ VITE_AUTH_ENABLED: "false" }),
    "disabled",
  );

  // ── redirect_uri absolute fix (the Invalid redirect URI bug) ──
  assert.equal(
    redirect.absolutizeOAuthRedirectUri(
      "/oauth2/callback/twitter",
      "https://app.example.com",
    ),
    "https://app.example.com/api/auth/oauth2/callback/twitter",
  );
  assert.equal(
    redirect.absolutizeOAuthRedirectUri(
      "https://app.example.com/api/auth/oauth2/callback/twitter",
      "https://app.example.com",
    ),
    "https://app.example.com/api/auth/oauth2/callback/twitter",
  );
  assert.equal(
    redirect.absolutizeOAuthRedirectUri(
      "/api/auth/oauth2/callback/google",
      "https://app.example.com",
    ),
    "https://app.example.com/api/auth/oauth2/callback/google",
  );

  const relativeAuth =
    "https://auth.grok.me/api/auth/oauth2/authorize?response_type=code&client_id=grok_preview&redirect_uri=%2Foauth2%2Fcallback%2Ftwitter&state=x&scope=openid";
  const fixed = redirect.fixOAuthAuthorizeUrl(
    relativeAuth,
    "https://foo.grok-sandbox.com",
    { providerId: "twitter" },
  );
  const fixedUri = new URL(fixed).searchParams.get("redirect_uri");
  assert.equal(
    fixedUri,
    "https://foo.grok-sandbox.com/api/auth/oauth2/callback/twitter",
    "relative redirect_uri must become absolute under app origin",
  );
  assert.equal(
    new URL(fixed).searchParams.get("idp"),
    "twitter",
    "broker authorize must include idp",
  );
  assert.equal(
    new URL(fixed).searchParams.get("prompt"),
    "login",
  );

  assert.deepEqual(
    redirect.expectedBrokerRedirectUris(
      "https://arrow-meadow-birch-civic.grok.me",
    ),
    [
      "https://arrow-meadow-birch-civic.grok.me/api/auth/oauth2/callback/google",
      "https://arrow-meadow-birch-civic.grok.me/api/auth/oauth2/callback/twitter",
    ],
  );

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

  // Email/password is ON as publish fallback when broker redirect_uris missing.
  const { emailAndPasswordEnabled } = await vite.ssrLoadModule(
    "/src/lib/auth/email-password.ts",
  );
  assert.equal(emailAndPasswordEnabled, true);

  console.log("OK auth social-config tests passed");
  process.exitCode = 0;
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close().catch(() => {});
}
