#!/usr/bin/env node
/**
 * High-impact: Schwab pull/ingest (read-only) + reauth failure paths.
 * Mocks broker HTTP only — no live Schwab. Asserts tenant isolation on writes.
 */
import assert from "node:assert/strict";
import { createViteTestServer } from "./vite-test-server.mjs";

const vite = await createViteTestServer();
const originalFetch = globalThis.fetch;

try {
  const { ensureDbReady, getSql } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { ensurePersonalTenant } = await vite.ssrLoadModule(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const {
    sealConnectorSecret,
    openConnectorSecret,
    rekeyConnectorSecretsIfNeeded,
  } = await vite.ssrLoadModule("/src/lib/portfolio/oauth/secrets.server.ts");
  const { pullAndIngestBroker, isReauthErrorMessage } = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/sync.server.ts",
  );
  const { fetchSchwabPortfolio } = await vite.ssrLoadModule(
    "/src/lib/portfolio/oauth/schwab.server.ts",
  );
  const { disconnectBroker, syncBrokers } = await vite.ssrLoadModule(
    "/src/lib/portfolio/connectors.server.ts",
  );
  const { newId } = await vite.ssrLoadModule("/src/lib/security/ids.ts");

  await ensureDbReady();
  const sql = await getSql();

  assert.equal(isReauthErrorMessage("invalid_grant"), true);
  assert.equal(isReauthErrorMessage("401 Unauthorized"), true);
  assert.equal(isReauthErrorMessage("Schwab re-authorization required"), true);
  assert.equal(isReauthErrorMessage("network timeout"), false);
  assert.equal(isReauthErrorMessage("rate limited 429"), false);

  const tenantA = await ensurePersonalTenant("sync-user-a");
  const tenantB = await ensurePersonalTenant("sync-user-b");
  const tenantEmpty = await ensurePersonalTenant("sync-user-empty");

  async function seedConnector(tenantId, tokens) {
    await sql`
      insert into connectors (id, tenant_id, broker, mode, status, auth_kind)
      values (${newId("conn")}, ${tenantId}, ${"schwab"}, ${"direct_oauth"}, ${"connected"}, ${"direct_oauth"})
      on conflict (tenant_id, broker) do update set
        status = ${"connected"},
        last_error = null,
        updated_at = now()
    `;
    const rows = await sql`
      select id from connectors where tenant_id = ${tenantId} and broker = ${"schwab"} limit 1
    `;
    const connectorId = rows[0].id;
    await sql`
      insert into connector_secrets (connector_id, tenant_id, ciphertext, key_version)
      values (${connectorId}, ${tenantId}, ${sealConnectorSecret(tokens)}, ${1})
      on conflict (connector_id) do update set
        ciphertext = excluded.ciphertext,
        tenant_id = excluded.tenant_id,
        updated_at = now()
    `;
    return connectorId;
  }

  const freshTokens = {
    kind: "direct_oauth",
    broker: "schwab",
    access_token: "test-access",
    refresh_token: "test-refresh",
    expires_at: Date.now() + 3_600_000,
    client_id: "test-client",
  };
  await seedConnector(tenantA.id, freshTokens);
  await seedConnector(tenantB.id, {
    ...freshTokens,
    access_token: "other-tenant-token",
  });

  globalThis.fetch = async (input) => {
    const url = String(input);
    if (url.includes("/accounts/accountNumbers")) {
      return new Response(
        JSON.stringify([
          { accountNumber: "111122223333", hashValue: "hash_a1" },
        ]),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    if (url.includes("/accounts/") && url.includes("fields=positions")) {
      return new Response(
        JSON.stringify({
          securitiesAccount: {
            accountNumber: "111122223333",
            type: "MARGIN",
            currentBalances: {
              liquidationValue: 12_500.5,
              cashBalance: 1_000,
            },
            positions: [
              {
                instrument: { symbol: "AAPL", assetType: "EQUITY" },
                longQuantity: 10,
                shortQuantity: 0,
                marketValue: 2_000,
                averagePrice: 200,
              },
              {
                instrument: { symbol: "MSFT", assetType: "EQUITY" },
                longQuantity: 5,
                shortQuantity: 0,
                marketValue: 1_500,
                averagePrice: 300,
              },
            ],
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }
    throw new Error(`unexpected fetch in sync test: ${url}`);
  };

  const portfolio = await fetchSchwabPortfolio("test-access");
  assert.equal(portfolio.accounts.length, 1);
  assert.equal(portfolio.positions.length, 2);
  assert.equal(portfolio.positions[0].symbol, "AAPL");

  await pullAndIngestBroker({ tenantId: tenantA.id, broker: "schwab" });

  const acctsA = await sql`
    select id, account_mask, display_name from broker_accounts
    where tenant_id = ${tenantA.id} and broker = ${"schwab"} and is_demo = false
  `;
  assert.equal(acctsA.length, 1, "one schwab account for A");
  assert.ok(!String(acctsA[0].display_name).includes("111122223333"));

  const posA = await sql`
    select symbol, quantity::float as quantity from gt_account_positions
    where tenant_id = ${tenantA.id} and source = ${"live"}
    order by symbol
  `;
  assert.equal(posA.length, 2);
  assert.equal(posA.find((p) => p.symbol === "AAPL")?.quantity, 10);

  const liveB = await sql`
    select count(*)::int as n from gt_account_positions
    where tenant_id = ${tenantB.id} and source = ${"live"}
  `;
  assert.equal(liveB[0].n, 0, "no cross-tenant live positions");

  const schwabB = await sql`
    select count(*)::int as n from broker_accounts
    where tenant_id = ${tenantB.id} and broker = ${"schwab"} and is_demo = false
  `;
  assert.equal(schwabB[0].n, 0, "B has no schwab accounts until its own sync");

  const connA = await sql`
    select status, last_error from connectors
    where tenant_id = ${tenantA.id} and broker = ${"schwab"}
  `;
  assert.equal(connA[0].status, "connected");
  assert.equal(connA[0].last_error, null);

  const { synced } = await syncBrokers(tenantA.id, "schwab");
  assert.equal(synced, 1);

  globalThis.fetch = async () =>
    new Response("unauthorized", { status: 401 });

  await assert.rejects(
    () => pullAndIngestBroker({ tenantId: tenantA.id, broker: "schwab" }),
    /401|accountNumbers|failed/i,
  );
  const afterErr = await sql`
    select status, last_error from connectors
    where tenant_id = ${tenantA.id} and broker = ${"schwab"}
  `;
  // 401 → needs_reauth; last-known holdings retained (not wiped)
  assert.equal(afterErr[0].status, "needs_reauth");
  assert.ok(afterErr[0].last_error);
  assert.equal(isReauthErrorMessage(afterErr[0].last_error), true);

  // No connector for this tenant → fail closed
  await assert.rejects(
    () => pullAndIngestBroker({ tenantId: tenantEmpty.id, broker: "schwab" }),
    /not connected/i,
  );

  await disconnectBroker({ tenantId: tenantA.id, broker: "schwab" });
  const secrets = await sql`
    select count(*)::int as n from connector_secrets s
    join connectors c on c.id = s.connector_id
    where c.tenant_id = ${tenantA.id} and c.broker = ${"schwab"}
  `;
  assert.equal(secrets[0].n, 0);
  const disc = await sql`
    select status from connectors where tenant_id = ${tenantA.id} and broker = ${"schwab"}
  `;
  assert.equal(disc[0].status, "disconnected");

  const sealed = sealConnectorSecret({ access_token: "x", refresh_token: "y" });
  const opened = openConnectorSecret(sealed);
  assert.equal(opened.access_token, "x");
  const rekey = await rekeyConnectorSecretsIfNeeded(sql);
  assert.ok(typeof rekey.checked === "number");

  console.log("OK broker sync critical path", {
    accounts: acctsA.length,
    positions: posA.length,
    isolation: true,
  });
} finally {
  globalThis.fetch = originalFetch;
  await vite.close();
}
