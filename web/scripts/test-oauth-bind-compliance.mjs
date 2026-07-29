#!/usr/bin/env node
/**
 * OAuth session-bind guard + compliance intended-use (pure + light DB).
 */
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

try {
  const guard = await vite.ssrLoadModule(
    "/src/lib/security/oauth-callback-guard.ts",
  );
  const compliance = await vite.ssrLoadModule(
    "/src/lib/compliance/intended-use.ts",
  );
  const { ensureDbReady, getSql } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { ensurePersonalTenant } = await vite.ssrLoadModule(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const oauth = await vite.ssrLoadModule(
    "/src/lib/portfolio/oauth.server.ts",
  );
  const { newId } = await vite.ssrLoadModule("/src/lib/security/ids.ts");

  // --- MECE principal bind ---
  assert.deepEqual(
    guard.assertOAuthCallbackPrincipal({
      stateUserId: "user-a",
      sessionUserId: "user-a",
    }),
    { ok: true },
  );
  assert.equal(
    guard.assertOAuthCallbackPrincipal({
      stateUserId: "user-a",
      sessionUserId: null,
    }).reason,
    "no_session",
  );
  assert.equal(
    guard.assertOAuthCallbackPrincipal({
      stateUserId: "user-a",
      sessionUserId: "user-b",
    }).reason,
    "user_mismatch",
  );
  assert.equal(
    guard.assertOAuthCallbackPrincipal({
      stateUserId: null,
      sessionUserId: "user-a",
    }).reason,
    "missing_state_user",
  );

  // --- Compliance product intent ---
  assert.equal(compliance.PRODUCT_INTENDED_USE.providesFinancialAdvice, false);
  assert.equal(
    compliance.PRODUCT_INTENDED_USE.professionalClientServices,
    false,
  );
  assert.equal(compliance.PRODUCT_INTENDED_USE.ownAccountsOnly, true);
  assert.ok(compliance.DISCLAIMER_SHORT.toLowerCase().includes("not investment advice"));
  assert.ok(
    compliance.isProfessionalServicesFeature({
      offersAdviceToClients: true,
    }),
  );
  assert.equal(
    compliance.isProfessionalServicesFeature({}),
    false,
  );
  // UI copy must stay plain (no "RIA" required in short footer line)
  assert.ok(!/pkce|oauth|tenant_id/i.test(compliance.DISCLAIMER_SHORT));

  // --- peek vs consume (one-shot, tenant-bound) ---
  await ensureDbReady();
  const sql = await getSql();
  const tA = await ensurePersonalTenant("bind-user-a");
  const tB = await ensurePersonalTenant("bind-user-b");
  const stateId = newId("oauth");
  const expires = new Date(Date.now() + 5 * 60_000).toISOString();

  await sql`
    insert into broker_oauth_states (
      id, tenant_id, user_id, broker, code_verifier, redirect_uri, expires_at,
      auth_kind
    ) values (
      ${stateId}, ${tA.id}, ${"bind-user-a"}, ${"schwab"}, ${"verifier"},
      ${"https://app.example.com/api/v1/oauth/schwab/callback"},
      ${expires}::timestamptz, ${"direct_oauth"}
    )
  `;

  const peeked = await oauth.peekOAuthState({
    stateId,
    broker: "schwab",
  });
  assert.ok(peeked);
  assert.equal(peeked.tenantId, tA.id);
  assert.equal(peeked.userId, "bind-user-a");

  // peek does not delete
  const peeked2 = await oauth.peekOAuthState({
    stateId,
    broker: "schwab",
  });
  assert.ok(peeked2);

  // mismatch simulation: attacker session would fail guard
  const attack = guard.assertOAuthCallbackPrincipal({
    stateUserId: peeked2.userId,
    sessionUserId: "bind-user-b",
  });
  assert.equal(attack.ok, false);
  assert.equal(attack.reason, "user_mismatch");

  // legitimate bind then consume
  assert.equal(
    guard.assertOAuthCallbackPrincipal({
      stateUserId: peeked2.userId,
      sessionUserId: "bind-user-a",
    }).ok,
    true,
  );
  const consumed = await oauth.consumeOAuthState({
    stateId,
    broker: "schwab",
  });
  assert.ok(consumed);
  assert.equal(consumed.tenantId, tA.id);

  // second consume fails
  const again = await oauth.consumeOAuthState({
    stateId,
    broker: "schwab",
  });
  assert.equal(again, null);

  // tenant B never had this state
  const cross = await sql`
    select id from broker_oauth_states
    where id = ${stateId} and tenant_id = ${tB.id}
  `;
  assert.equal(cross.length, 0);

  console.log("OK oauth bind + compliance tests passed");
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close();
}
