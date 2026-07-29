#!/usr/bin/env node
/**
 * Unit + integration tests for tenant-scoped token refresh job.
 * Uses mocked fetch for broker token endpoints; no real secrets.
 */
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

const originalFetch = globalThis.fetch;

try {
  const { ensureDbReady, getSql } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { ensurePersonalTenant } = await vite.ssrLoadModule(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const refresh = await vite.ssrLoadModule(
    "/src/lib/portfolio/oauth/refresh.server.ts",
  );
  const { sealConnectorSecret, openConnectorSecret } = await vite.ssrLoadModule(
    "/src/lib/portfolio/oauth/secrets.server.ts",
  );
  const { newId } = await vite.ssrLoadModule("/src/lib/security/ids.ts");

  await ensureDbReady();
  const sql = await getSql();

  // --- pure helpers ---
  const now = 1_700_000_000_000;
  assert.equal(
    refresh.classifyRefreshAction(
      {
        kind: "direct_oauth",
        broker: "schwab",
        access_token: "a",
        refresh_token: "r",
        expires_at: now + 60 * 60 * 1000,
        obtainedAt: new Date().toISOString(),
      },
      { now, skewMs: refresh.DEFAULT_REFRESH_SKEW_MS },
    ),
    "skip",
    "fresh token should skip",
  );
  assert.equal(
    refresh.classifyRefreshAction(
      {
        kind: "direct_oauth",
        broker: "schwab",
        access_token: "a",
        refresh_token: "r",
        expires_at: now + 60 * 1000,
        obtainedAt: new Date().toISOString(),
      },
      { now, skewMs: refresh.DEFAULT_REFRESH_SKEW_MS },
    ),
    "refresh",
    "near-expiry should refresh",
  );
  assert.equal(
    refresh.classifyRefreshAction(
      {
        kind: "direct_oauth",
        broker: "schwab",
        access_token: "a",
        expires_at: now - 1,
        obtainedAt: new Date().toISOString(),
      },
      { now },
    ),
    "needs_reauth",
    "expired without refresh token",
  );
  assert.equal(
    refresh.classifyRefreshAction(null),
    "needs_reauth",
    "null tokens",
  );
  assert.equal(
    refresh.classifyRefreshAction(
      {
        kind: "direct_oauth",
        broker: "schwab",
        access_token: "a",
        refresh_token: "r",
        expires_at: now + 60 * 60 * 1000,
        obtainedAt: new Date().toISOString(),
      },
      { force: true, now },
    ),
    "refresh",
    "force overrides freshness",
  );

  // --- multi-tenant isolation with mocked refresh ---
  const tA = await ensurePersonalTenant("refresh-user-a");
  const tB = await ensurePersonalTenant("refresh-user-b");
  assert.notEqual(tA.id, tB.id);

  const connA = newId("conn");
  const connB = newId("conn");
  const expiredAt = Date.now() - 1000;

  const tokensA = {
    kind: "direct_oauth",
    broker: "schwab",
    access_token: "tenant-a-access-old",
    refresh_token: "tenant-a-refresh",
    expires_at: expiredAt,
    client_id: "app-client",
    obtainedAt: new Date().toISOString(),
  };
  const tokensB = {
    kind: "direct_oauth",
    broker: "schwab",
    access_token: "tenant-b-access-old",
    refresh_token: "tenant-b-refresh",
    expires_at: expiredAt,
    client_id: "app-client",
    obtainedAt: new Date().toISOString(),
  };

  for (const [tenantId, connId, tokens] of [
    [tA.id, connA, tokensA],
    [tB.id, connB, tokensB],
  ]) {
    await sql`
      insert into connectors (id, tenant_id, broker, mode, status, auth_kind)
      values (${connId}, ${tenantId}, ${"schwab"}, ${"direct_oauth"}, ${"connected"}, ${"direct_oauth"})
      on conflict (id) do nothing
    `;
    // unique (tenant_id, broker) may conflict if prior runs — use update path
    await sql`
      insert into connectors (id, tenant_id, broker, mode, status, auth_kind)
      values (${connId}, ${tenantId}, ${"schwab"}, ${"direct_oauth"}, ${"connected"}, ${"direct_oauth"})
      on conflict (tenant_id, broker) do update set
        id = excluded.id,
        status = ${"connected"},
        mode = ${"direct_oauth"}
    `;
    const idRow = await sql`select id from connectors where tenant_id = ${tenantId} and broker = ${"schwab"} limit 1`;
    const realId = idRow[0].id;
    await sql`
      insert into connector_secrets (connector_id, tenant_id, ciphertext, key_version)
      values (${realId}, ${tenantId}, ${sealConnectorSecret(tokens)}, ${1})
      on conflict (connector_id) do update set
        ciphertext = excluded.ciphertext,
        tenant_id = excluded.tenant_id
    `;
  }

  // Mock Schwab refresh endpoint — return tenant-specific tokens based on refresh_token
  process.env.SCHWAB_CLIENT_ID = process.env.SCHWAB_CLIENT_ID || "test-client-id";
  process.env.SCHWAB_CLIENT_SECRET =
    process.env.SCHWAB_CLIENT_SECRET || "test-client-secret";

  globalThis.fetch = async (url, init) => {
    const u = String(url);
    if (u.includes("oauth/token") || u.includes("schwabapi.com")) {
      const body = init?.body?.toString?.() || "";
      const params = new URLSearchParams(body);
      const rt = params.get("refresh_token");
      const access =
        rt === "tenant-a-refresh"
          ? "tenant-a-access-NEW"
          : rt === "tenant-b-refresh"
            ? "tenant-b-access-NEW"
            : "unknown";
      return new Response(
        JSON.stringify({
          access_token: access,
          refresh_token: rt,
          expires_in: 1800,
          token_type: "Bearer",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    return originalFetch(url, init);
  };

  const job = await refresh.runTokenRefreshJob({ force: true });
  assert.ok(job.examined >= 2, "should examine both tenants");
  assert.equal(job.errors, 0, `no errors: ${JSON.stringify(job.results)}`);
  assert.ok(job.refreshed >= 2, "both connectors refreshed");

  const secA = await sql`
    select s.ciphertext from connector_secrets s
    join connectors c on c.id = s.connector_id
    where c.tenant_id = ${tA.id} and c.broker = ${"schwab"}
  `;
  const secB = await sql`
    select s.ciphertext from connector_secrets s
    join connectors c on c.id = s.connector_id
    where c.tenant_id = ${tB.id} and c.broker = ${"schwab"}
  `;
  const openedA = openConnectorSecret(secA[0].ciphertext);
  const openedB = openConnectorSecret(secB[0].ciphertext);
  assert.equal(openedA.access_token, "tenant-a-access-NEW");
  assert.equal(openedB.access_token, "tenant-b-access-NEW");
  assert.notEqual(
    openedA.access_token,
    openedB.access_token,
    "tokens must not cross tenants",
  );

  // Scoped job: only tenant A
  // Reset A to expired again
  const idA = (
    await sql`select id from connectors where tenant_id = ${tA.id} and broker = ${"schwab"}`
  )[0].id;
  await sql`
    update connector_secrets set ciphertext = ${sealConnectorSecret({
      ...tokensA,
      access_token: "tenant-a-access-old2",
      expires_at: Date.now() - 1,
    })}
    where connector_id = ${idA} and tenant_id = ${tA.id}
  `;
  const scoped = await refresh.runTokenRefreshJob({
    tenantId: tA.id,
    force: true,
  });
  assert.equal(
    scoped.results.every((r) => r.tenantId === tA.id),
    true,
    "scoped job only touches tenant A",
  );
  assert.equal(
    scoped.results.some((r) => r.tenantId === tB.id),
    false,
  );

  // Seal/open round-trip does not leak forbidden keys in audit path
  assert.ok(!JSON.stringify(job).includes("tenant-a-refresh"));
  assert.ok(!JSON.stringify(job).includes("tenant-b-refresh"));

  console.log("OK token refresh job tests passed", {
    examined: job.examined,
    refreshed: job.refreshed,
    scopedExamined: scoped.examined,
  });
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  globalThis.fetch = originalFetch;
  await vite.close();
}
