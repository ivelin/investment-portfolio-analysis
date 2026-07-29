#!/usr/bin/env node
/**
 * Pure MECE unit tests — no DB, no network.
 * Locks refresh + connector CTA decision matrices (DRY with app modules).
 */
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

try {
  const refresh = await vite.ssrLoadModule(
    "/src/lib/portfolio/oauth/refresh-decision.ts",
  );
  const status = await vite.ssrLoadModule(
    "/src/lib/portfolio/connector-status.ts",
  );

  const now = 1_700_000_000_000;
  const cases = [
    {
      name: "null → needs_reauth",
      tokens: null,
      opts: {},
      expect: "needs_reauth",
    },
    {
      name: "fresh → skip",
      tokens: {
        access_token: "a",
        refresh_token: "r",
        expires_at: now + 3_600_000,
      },
      opts: { now },
      expect: "skip",
    },
    {
      name: "near expiry → refresh",
      tokens: {
        access_token: "a",
        refresh_token: "r",
        expires_at: now + 30_000,
      },
      opts: { now },
      expect: "refresh",
    },
    {
      name: "force fresh → refresh",
      tokens: {
        access_token: "a",
        refresh_token: "r",
        expires_at: now + 3_600_000,
      },
      opts: { now, force: true },
      expect: "refresh",
    },
    {
      name: "expired no refresh → needs_reauth",
      tokens: { access_token: "a", expires_at: now - 1 },
      opts: { now },
      expect: "needs_reauth",
    },
  ];

  for (const c of cases) {
    assert.equal(
      refresh.classifyRefreshAction(c.tokens, c.opts),
      c.expect,
      c.name,
    );
  }

  // Exhaustive: every action appears; no unknown
  const seen = new Set(cases.map((c) => c.expect));
  for (const a of ["skip", "refresh", "needs_reauth"]) {
    assert.ok(seen.has(a), `matrix must cover ${a}`);
  }

  // Connector UI status MECE priority
  assert.equal(
    status.classifyConnectorUiStatus({
      status: "connected",
      oauthConfigured: false,
    }),
    "connected",
  );
  assert.equal(
    status.classifyConnectorUiStatus({
      status: "error",
      oauthConfigured: true,
    }),
    "needs_attention",
  );
  assert.equal(
    status.classifyConnectorUiStatus({
      status: "pending_oauth",
      oauthConfigured: true,
    }),
    "finish_at_broker",
  );
  assert.equal(
    status.classifyConnectorUiStatus({
      status: "disconnected",
      oauthConfigured: false,
    }),
    "setup_needed",
  );
  assert.equal(
    status.classifyConnectorUiStatus({
      status: "disconnected",
      oauthConfigured: true,
    }),
    "not_connected",
  );

  assert.equal(
    status.primaryConnectCta({
      status: "disconnected",
      oauthConfigured: false,
    }),
    "how_to_connect",
  );
  assert.equal(
    status.primaryConnectCta({
      status: "disconnected",
      oauthConfigured: true,
    }),
    "connect",
  );
  assert.equal(
    status.primaryConnectCta({
      status: "connected",
      oauthConfigured: true,
    }),
    "refresh_disconnect",
  );

  // Labels are product language (no OAuth jargon)
  for (const s of [
    "connected",
    "needs_attention",
    "finish_at_broker",
    "setup_needed",
    "not_connected",
  ]) {
    const label = status.connectorUiLabel(s);
    assert.ok(label.length > 0);
    assert.ok(!/oauth|pkce|tenant|dcr/i.test(label), label);
  }

  console.log("OK mece decision tests passed");
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close();
}
