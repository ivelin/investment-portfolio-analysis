#!/usr/bin/env node
/**
 * High-impact OAuth callback edges: invalid input, expired state,
 * session bind rejection (CSRF / account-linking), no silent token store.
 */
import assert from "node:assert/strict";
import { createViteTestServer } from "./vite-test-server.mjs";

const vite = await createViteTestServer();

try {
  const { ensureDbReady, getSql } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { ensurePersonalTenant } = await vite.ssrLoadModule(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const { oauthCallbackGet } = await vite.ssrLoadModule(
    "/src/routes/api/v1/oauth/$broker/callback.ts",
  );
  const { newId } = await vite.ssrLoadModule("/src/lib/security/ids.ts");

  await ensureDbReady();
  const sql = await getSql();
  const tenant = await ensurePersonalTenant("oauth-cb-user");

  async function call(path, broker = "schwab") {
    return oauthCallbackGet({
      request: new Request(`http://127.0.0.1:8080${path}`),
      params: { broker },
    });
  }

  {
    const res = await call("/api/v1/oauth/schwab/callback?error=access_denied");
    assert.equal(res.status, 302);
    assert.match(res.headers.get("location") || "", /oauth=error/);
    assert.match(res.headers.get("location") || "", /access_denied/);
  }

  {
    const res = await call("/api/v1/oauth/schwab/callback");
    assert.equal(res.status, 302);
    assert.match(res.headers.get("location") || "", /invalid_callback/);
  }

  {
    const res = await call(
      "/api/v1/oauth/notabroker/callback?code=x&state=y",
      "notabroker",
    );
    assert.equal(res.status, 302);
    assert.match(res.headers.get("location") || "", /invalid_callback/);
  }

  {
    const res = await call(
      "/api/v1/oauth/schwab/callback?code=abc&state=state_does_not_exist",
    );
    assert.equal(res.status, 302);
    assert.match(res.headers.get("location") || "", /expired_state/);
  }

  const stateId = newId("state");
  await sql`
    insert into broker_oauth_states (
      id, tenant_id, user_id, broker, code_verifier, redirect_uri, expires_at, auth_kind
    ) values (
      ${stateId}, ${tenant.id}, ${"oauth-cb-user"}, ${"schwab"},
      ${"verifier"}, ${"http://127.0.0.1:8080/api/v1/oauth/schwab/callback"},
      ${new Date(Date.now() + 600_000).toISOString()}::timestamptz,
      ${"direct_oauth"}
    )
  `;

  {
    const secretsBefore = await sql`
      select count(*)::int as n from connector_secrets
      where tenant_id = ${tenant.id}
    `;
    const res = await call(
      `/api/v1/oauth/schwab/callback?code=fake&state=${stateId}`,
    );
    assert.equal(res.status, 302);
    const loc = res.headers.get("location") || "";
    assert.match(
      loc,
      /sign_in_required/,
      `expected sign_in_required, got ${loc}`,
    );
    const secretsAfter = await sql`
      select count(*)::int as n from connector_secrets
      where tenant_id = ${tenant.id}
    `;
    assert.equal(
      secretsAfter[0].n,
      secretsBefore[0].n,
      "bind failure must not store connector secrets",
    );
    const audit = await sql`
      select action from audit_events
      where tenant_id = ${tenant.id}
        and action = ${"connector.oauth_bind_rejected"}
      order by created_at desc limit 1
    `;
    assert.equal(audit[0]?.action, "connector.oauth_bind_rejected");
  }

  const still = await sql`
    select id from broker_oauth_states where id = ${stateId}
  `;
  assert.equal(still.length, 1, "no_session should keep state for retry");

  console.log("OK oauth callback edge cases");
} finally {
  await vite.close();
}
