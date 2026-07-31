#!/usr/bin/env node
/**
 * Critical path: demo sample → simulated Schwab (live) dashboard switch.
 * Asserts primary selection, holdings symbols, and sample hide rules.
 */
import assert from "node:assert/strict";
import { createViteTestServer } from "./vite-test-server.mjs";

const vite = await createViteTestServer();

try {
  const selection = await vite.ssrLoadModule(
    "/src/lib/portfolio/dashboard-selection.ts",
  );
  const { ensureDbReady } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { ensurePersonalTenant } = await vite.ssrLoadModule(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const service = await vite.ssrLoadModule(
    "/src/lib/portfolio/service.server.ts",
  );
  const sim = await vite.ssrLoadModule(
    "/src/lib/portfolio/simulated-schwab.server.ts",
  );

  // --- pure selection (dangerous edge cases) ---
  const demo = { id: "d1", isDemo: true, latestNlv: 100_000 };
  const liveA = { id: "l1", isDemo: false, latestNlv: 800_000 };
  const liveB = { id: "l2", isDemo: false, latestNlv: 500_000 };

  assert.equal(selection.pickPrimaryAccount([demo])?.id, "d1");
  assert.equal(selection.pickPrimaryAccount([demo, liveA, liveB])?.id, "l1");
  assert.equal(
    selection.pickPrimaryAccount([demo, liveA, liveB], "l2")?.id,
    "l2",
  );
  // Preferring sample while live exists → ignore, keep live
  assert.equal(
    selection.pickPrimaryAccount([demo, liveA], "d1")?.id,
    "l1",
    "must not stick to sample when live exists",
  );
  assert.deepEqual(
    selection.visibleDashboardAccounts([demo, liveA]).map((a) => a.id),
    ["l1"],
  );
  assert.equal(selection.workspaceIsDemoOnly([demo]), true);
  assert.equal(selection.workspaceIsDemoOnly([demo, liveA]), false);

  assert.equal(
    selection.positionsLookLikeDemo(["VOO", "CASH", "MSFT", "AAPL", "NVDA"]),
    true,
  );
  assert.equal(
    selection.positionsLookLikeSimulatedSchwab(["SGOV", "TSLA", "IBIT"]),
    true,
  );
  assert.equal(
    selection.positionsLookLikeDemo(["SGOV", "TSLA", "IBIT"]),
    false,
  );

  await ensureDbReady();
  const tenant = await ensurePersonalTenant("dash-switch-user");
  const meta = {
    id: tenant.id,
    name: tenant.name,
    slug: tenant.slug,
    plan: tenant.plan,
  };

  // --- Phase 1: demo only ---
  const dash1 = await service.getDashboardPayload(tenant.id, meta);
  assert.equal(dash1.workspace.isDemo, true);
  assert.ok(dash1.selectedAccountId);
  const primary1 = dash1.accounts.find((a) => a.id === dash1.selectedAccountId);
  assert.equal(primary1?.isDemo, true);
  assert.ok(
    selection.positionsLookLikeDemo(dash1.positions.map((p) => p.symbol)),
    "demo positions expected",
  );
  assert.ok(dash1.series.length > 2, "demo has series");

  // --- Phase 2: seed simulated Schwab ---
  const seeded = await sim.seedSimulatedSchwab(tenant.id);
  assert.equal(seeded.accountCount, 3);
  assert.ok(seeded.totalNlv > 1_000_000);
  assert.ok(await sim.hasSimulatedSchwab(tenant.id));

  const dash2 = await service.getDashboardPayload(tenant.id, meta);
  assert.equal(dash2.workspace.isDemo, false, "workspace no longer demo-only");
  const live = dash2.accounts.filter((a) => !a.isDemo);
  assert.equal(live.length, 3, "3 schwab sim accounts");
  const primary2 = dash2.accounts.find((a) => a.id === dash2.selectedAccountId);
  assert.ok(primary2 && !primary2.isDemo, "primary is live schwab");
  assert.equal(primary2.broker, "schwab");
  assert.match(primary2.displayName, /sim/i);

  const posSyms = dash2.positions.map((p) => p.symbol);
  assert.ok(
    selection.positionsLookLikeSimulatedSchwab(posSyms),
    `expected sim symbols, got ${posSyms.join(",")}`,
  );
  assert.equal(
    selection.positionsLookLikeDemo(posSyms),
    false,
    "must not show demo holdings after sim import",
  );
  assert.ok(!posSyms.includes("VOO"), "VOO is demo-only");
  assert.ok(posSyms.includes("SGOV") || posSyms.includes("TSLA"));

  // Total NLV is sum of live accounts (not demo 100k)
  const sumLive = live.reduce((s, a) => s + (a.latestNlv ?? 0), 0);
  assert.ok(Math.abs(sumLive - seeded.totalNlv) < 1, "NLV matches sim total");
  assert.ok(dash2.workspace.latestNlv != null && dash2.workspace.latestNlv > 500_000);

  // Account portfolio isolation: demo account still has demo symbols if requested
  const demoAcct = dash2.accounts.find((a) => a.isDemo);
  assert.ok(demoAcct);
  const demoPort = await service.getAccountPortfolio(tenant.id, demoAcct.id);
  assert.ok(
    selection.positionsLookLikeDemo(demoPort.positions.map((p) => p.symbol)),
  );

  // Switch primary via preferred id among live
  const secondLive = live.find((a) => a.id !== primary2.id);
  const dash3 = await service.getDashboardPayload(
    tenant.id,
    meta,
    secondLive.id,
  );
  assert.equal(dash3.selectedAccountId, secondLive.id);
  assert.ok(!dash3.positions.every((p) => p.symbol === "VOO"));

  // Clear sim → back to demo primary
  await sim.clearSimulatedSchwab(tenant.id);
  assert.equal(await sim.hasSimulatedSchwab(tenant.id), false);
  const dash4 = await service.getDashboardPayload(tenant.id, meta);
  assert.equal(dash4.workspace.isDemo, true);
  const p4 = dash4.accounts.find((a) => a.id === dash4.selectedAccountId);
  assert.equal(p4?.isDemo, true);
  assert.ok(
    selection.positionsLookLikeDemo(dash4.positions.map((p) => p.symbol)),
  );

  // Refuse overwrite when real oauth secrets present
  const { getSql } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { sealConnectorSecret } = await vite.ssrLoadModule(
    "/src/lib/portfolio/oauth/secrets.server.ts",
  );
  const { newId } = await vite.ssrLoadModule("/src/lib/security/ids.ts");
  const sql = await getSql();
  const cid = newId("conn");
  await sql`
    insert into connectors (id, tenant_id, broker, mode, status, auth_kind)
    values (${cid}, ${tenant.id}, ${"schwab"}, ${"direct_oauth"}, ${"connected"}, ${"direct_oauth"})
  `;
  await sql`
    insert into connector_secrets (connector_id, tenant_id, ciphertext, key_version)
    values (
      ${cid}, ${tenant.id},
      ${sealConnectorSecret({ access_token: "x", refresh_token: "y" })},
      ${1}
    )
  `;
  await assert.rejects(
    () => sim.seedSimulatedSchwab(tenant.id),
    /real Schwab connection/i,
  );

  console.log("OK dashboard live switch", {
    demoThenLive: true,
    simNlv: seeded.totalNlv,
    cleared: true,
  });
} finally {
  await vite.close();
}
