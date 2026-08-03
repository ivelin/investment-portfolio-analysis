#!/usr/bin/env node
/**
 * Preview-only: seal Schwab OAuth tokens into PGLite and pull READ-ONLY portfolio.
 *
 * HARD RULES:
 *  - Refuses if DATABASE_URL / Neon would be used
 *  - Asserts broker mode is read_only_analysis
 *  - Only GET portfolio + optional token refresh POST — never /orders
 *  - Tokens never written to git-tracked paths (env only; sealed at rest in PGLite)
 *
 * Usage:
 *   SCHWAB_DEV_TOKEN_JSON='{"access_token":"...","refresh_token":"...",...}' \
 *     node scripts/seed-dev-schwab-oauth.mjs [userId]
 */
import { createViteTestServer } from "./vite-test-server.mjs";

const userId = process.argv[2] || "preview-live-schwab";

delete process.env.DATABASE_URL;
delete process.env.POSTGRES_URL;
delete process.env.POSTGRES_PRISMA_URL;
delete process.env.POSTGRES_URL_NON_POOLING;
delete process.env.NEON_DATABASE_URL;
process.env.GROK_AGENT = process.env.GROK_AGENT || "1";

const raw = process.env.SCHWAB_DEV_TOKEN_JSON?.trim();
if (!raw) {
  console.error("Set SCHWAB_DEV_TOKEN_JSON to the token object JSON");
  process.exit(1);
}

const tok = JSON.parse(raw);
const access = String(tok.access_token || tok.token?.access_token || "");
const refresh = String(tok.refresh_token || tok.token?.refresh_token || "");
if (!access) {
  console.error("access_token missing");
  process.exit(1);
}

let expiresAt = Number(tok.expires_at || tok.token?.expires_at || 0);
if (expiresAt > 0 && expiresAt < 1e12) expiresAt *= 1000; // seconds → ms
if (!expiresAt) {
  const expIn = Number(tok.expires_in || tok.token?.expires_in || 1800);
  expiresAt = Date.now() + expIn * 1000;
}

const vite = await createViteTestServer();
const originalFetch = globalThis.fetch;

try {
  const { resolveDatabaseUrl } = await vite.ssrLoadModule("/src/lib/db-url.ts");
  if (resolveDatabaseUrl()) {
    throw new Error("REFUSED: resolveDatabaseUrl() is set — never seed tokens into publish Neon");
  }

  const policy = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/read-only-policy.ts",
  );
  policy.assertBrokerConnectorsReadOnly();
  if (policy.BROKER_CONNECTOR_MODE !== "read_only_analysis") {
    throw new Error("REFUSED: connector mode is not read_only_analysis");
  }

  // Guard: any accidental order URL in this process fails closed
  const blocked = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    const method = String(init?.method || "GET").toUpperCase();
    if (/api\.schwabapi\.com/i.test(url) && /\/orders?/i.test(url)) {
      blocked.push({ url, method });
      throw new Error(`BLOCKED write path: ${method} ${url}`);
    }
    if (
      /api\.schwabapi\.com\/trader\//i.test(url) &&
      method !== "GET" &&
      !/\/oauth\/token/i.test(url)
    ) {
      blocked.push({ url, method });
      throw new Error(`BLOCKED non-GET trader call: ${method} ${url}`);
    }
    return originalFetch(input, init);
  };

  const { ensureDbReady, getSql, dbSource } = await vite.ssrLoadModule(
    "/src/lib/db.ts",
  );
  if (dbSource !== "pglite") {
    throw new Error(`REFUSED: dbSource=${dbSource} (must be pglite for dev seed)`);
  }

  const { ensurePersonalTenant } = await vite.ssrLoadModule(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const { sealConnectorSecret } = await vite.ssrLoadModule(
    "/src/lib/portfolio/oauth/secrets.server.ts",
  );
  const { newId } = await vite.ssrLoadModule("/src/lib/security/ids.ts");
  const { pullAndIngestBroker } = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/sync.server.ts",
  );
  const { getDashboardPayload } = await vite.ssrLoadModule(
    "/src/lib/portfolio/service.server.ts",
  );
  const { assertBrokerFetchWouldAllow } = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/broker-http.ts",
  );

  // Static policy self-test before any network
  assertBrokerFetchWouldAllow(
    "https://api.schwabapi.com/trader/v1/accounts/accountNumbers",
    { method: "GET", purpose: "portfolio_read" },
  );
  let denied = false;
  try {
    assertBrokerFetchWouldAllow(
      "https://api.schwabapi.com/trader/v1/accounts/x/orders",
      { method: "POST", purpose: "portfolio_read" },
    );
  } catch {
    denied = true;
  }
  if (!denied) throw new Error("Policy failed to deny POST /orders");

  await ensureDbReady();
  const sql = await getSql();
  const tenant = await ensurePersonalTenant(userId);

  const payload = {
    kind: "direct_oauth",
    broker: "schwab",
    access_token: access,
    refresh_token: refresh || undefined,
    expires_at: expiresAt,
    client_id: tok.client_id || tok.token?.client_id || undefined,
    scope: tok.scope || "api",
    token_type: tok.token_type || "Bearer",
    obtainedAt: new Date().toISOString(),
    source: "dev_sandbox_token_seed",
    read_only: true,
  };

  const connId = newId("conn");
  await sql`
    insert into connectors (
      id, tenant_id, broker, mode, status, auth_kind, last_error
    ) values (
      ${connId}, ${tenant.id}, ${"schwab"}, ${"direct_oauth"}, ${"connected"},
      ${"direct_oauth"}, null
    )
    on conflict (tenant_id, broker) do update set
      mode = ${"direct_oauth"},
      status = ${"connected"},
      auth_kind = ${"direct_oauth"},
      last_error = null,
      updated_at = now()
  `;
  const rows = await sql`
    select id from connectors where tenant_id = ${tenant.id} and broker = ${"schwab"} limit 1
  `;
  const id = rows[0].id;
  const ciphertext = sealConnectorSecret(payload);
  await sql`
    insert into connector_secrets (connector_id, tenant_id, ciphertext, key_version)
    values (${id}, ${tenant.id}, ${ciphertext}, ${1})
    on conflict (connector_id) do update set
      ciphertext = excluded.ciphertext,
      tenant_id = excluded.tenant_id,
      updated_at = now()
  `;

  // READ-ONLY pull
  await pullAndIngestBroker({ tenantId: tenant.id, broker: "schwab" });

  const dash = await getDashboardPayload(tenant.id, {
    id: tenant.id,
    name: tenant.name,
    slug: tenant.slug,
    plan: tenant.plan,
  });

  const live = dash.accounts.filter((a) => !a.isDemo && a.broker === "schwab");
  const pos = dash.positions.map((p) => p.symbol).slice(0, 30);

  // Also attach to any other tenants already in preview so signed-in users see data
  const others = await sql`select id, owner_user_id from tenants where id <> ${tenant.id}`;
  for (const t of others) {
    await sql`
      insert into connectors (id, tenant_id, broker, mode, status, auth_kind)
      values (${newId("conn")}, ${t.id}, ${"schwab"}, ${"direct_oauth"}, ${"connected"}, ${"direct_oauth"})
      on conflict (tenant_id, broker) do update set
        mode = ${"direct_oauth"},
        status = ${"connected"},
        auth_kind = ${"direct_oauth"},
        last_error = null,
        updated_at = now()
    `;
    const c = await sql`select id from connectors where tenant_id = ${t.id} and broker = ${"schwab"} limit 1`;
    await sql`
      insert into connector_secrets (connector_id, tenant_id, ciphertext, key_version)
      values (${c[0].id}, ${t.id}, ${ciphertext}, ${1})
      on conflict (connector_id) do update set
        ciphertext = excluded.ciphertext,
        tenant_id = excluded.tenant_id,
        updated_at = now()
    `;
    try {
      await pullAndIngestBroker({ tenantId: t.id, broker: "schwab" });
    } catch (e) {
      console.warn("sync other tenant failed", t.owner_user_id, e.message);
    }
  }

  console.log(
    JSON.stringify(
      {
        ok: true,
        database: "pglite",
        readOnlyMode: policy.BROKER_CONNECTOR_MODE,
        blockedWriteAttempts: blocked.length,
        userId,
        tenantId: tenant.id,
        workspaceIsDemo: dash.workspace.isDemo,
        schwabAccounts: live.length,
        totalNlv: live.reduce((s, a) => s + (a.latestNlv ?? 0), 0),
        accounts: live.map((a) => ({
          name: a.displayName,
          mask: a.accountMask,
          nlv: a.latestNlv,
        })),
        selectedIsDemo: dash.accounts.find((a) => a.id === dash.selectedAccountId)
          ?.isDemo,
        sampleSymbolsOnSelected: pos,
        tokensSealed: true,
        tokensNotInGit: true,
      },
      null,
      2,
    ),
  );
} finally {
  globalThis.fetch = originalFetch;
  await vite.close();
}
