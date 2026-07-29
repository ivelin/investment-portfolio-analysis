#!/usr/bin/env node
/**
 * Isolation self-test: two tenants must never see each other's accounts.
 * Also asserts OAuth start does not use shared snapshots.
 */
import { createServer } from "vite";

const vite = await createServer({
  server: { middlewareMode: true },
  appType: "custom",
  root: "/workspace",
});

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

try {
  const { ensureDbReady, getSql } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { ensurePersonalTenant } = await vite.ssrLoadModule(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const service = await vite.ssrLoadModule(
    "/src/lib/portfolio/service.server.ts",
  );
  const { connectBroker } = await vite.ssrLoadModule(
    "/src/lib/portfolio/connectors.server.ts",
  );
  const { BROKER_IDS } = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/catalog.ts",
  );

  await ensureDbReady();
  const sql = await getSql();

  const tA = await ensurePersonalTenant("isolation-user-a");
  const tB = await ensurePersonalTenant("isolation-user-b");
  assert(tA.id !== tB.id, "tenants must differ");

  const acctsA = await service.listAccounts(tA.id);
  const acctsB = await service.listAccounts(tB.id);
  assert(acctsA.length >= 1, "tenant A should have demo account");
  assert(acctsB.length >= 1, "tenant B should have demo account");

  const idsA = new Set(acctsA.map((a) => a.id));
  for (const b of acctsB) {
    assert(!idsA.has(b.id), "account id leaked across tenants");
  }

  const leak = await service.getPositions(tA.id, acctsB[0].id);
  assert(leak.length === 0, "positions must not load for foreign account id");

  const seriesLeak = await service.getFundSeries(tA.id, acctsB[0].id);
  assert(
    seriesLeak.length === 0,
    "fund series must not load for foreign account id",
  );

  for (const broker of BROKER_IDS) {
    const conn = await connectBroker({
      tenantId: tA.id,
      userId: "isolation-user-a",
      broker,
      origin: "http://127.0.0.1:8080",
    });
    assert(
      conn.kind === "not_configured" || conn.kind === "oauth_redirect",
      `${broker}: connect must return oauth path or not_configured`,
    );
    if (conn.kind === "oauth_redirect") {
      assert(
        typeof conn.authorizeUrl === "string" &&
          conn.authorizeUrl.startsWith("https://"),
        `${broker}: authorize URL must be https`,
      );
      // State must be bound to tenant A only
      const states = await sql`
        select tenant_id from broker_oauth_states
        where broker = ${broker} and tenant_id = ${tA.id}
      `;
      assert(states.length >= 1, `${broker}: oauth state must be tenant-scoped`);
      const foreign = await sql`
        select count(*)::int as n from broker_oauth_states
        where broker = ${broker} and tenant_id = ${tB.id}
      `;
      assert(
        Number(foreign[0].n) === 0,
        `${broker}: oauth state must not appear under other tenant`,
      );
    }
  }

  const badSecrets = await sql`
    select count(*)::int as n from connector_secrets
    where ciphertext = ${"platform_oauth_ref"}
  `;
  assert(
    Number(badSecrets[0].n) === 0,
    "platform_oauth_ref secrets must not remain",
  );

  console.log("OK tenant isolation + oauth state scoping passed");
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close();
}
