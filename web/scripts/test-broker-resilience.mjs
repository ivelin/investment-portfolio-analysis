#!/usr/bin/env node
/**
 * High-impact resilience: OAuth failure, contract drift, grounded math.
 * No fluff — only dangerous edges for financial correctness.
 */
import assert from "node:assert/strict";
import { createViteTestServer } from "./vite-test-server.mjs";

const vite = await createViteTestServer();
const originalFetch = globalThis.fetch;

try {
  const finance = await vite.ssrLoadModule("/src/lib/portfolio/finance-math.ts");
  const health = await vite.ssrLoadModule("/src/lib/portfolio/data-health.ts");
  const contract = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/schwab-contract.ts",
  );
  const syncErr = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/sync-errors.ts",
  );
  const status = await vite.ssrLoadModule(
    "/src/lib/portfolio/connector-status.ts",
  );

  // ─── Finance math: never invent zeros ───────────────────────────
  {
    const empty = finance.sumKnownNlvs([]);
    assert.equal(empty.total, null);
    assert.equal(empty.complete, true);

    const partial = finance.sumKnownNlvs([100, null, 50]);
    assert.equal(partial.total, 150);
    assert.equal(partial.complete, false);
    assert.equal(partial.knownCount, 2);
    assert.equal(partial.missingCount, 1);

    // Missing must not become zero in a "complete" total
    const allMissing = finance.sumKnownNlvs([null, undefined]);
    assert.equal(allMissing.total, null);
    assert.equal(allMissing.complete, false);

    assert.equal(finance.finiteNumber("nope"), null);
    assert.equal(finance.finiteNumber(NaN), null);
    assert.equal(finance.finiteNumber(Infinity), null);
    assert.equal(finance.finiteNumber(0), 0);
  }

  // Period return: refuse single-day / same-day / non-positive start
  {
    assert.equal(finance.periodReturnPct([]), null);
    assert.equal(
      finance.periodReturnPct([{ liquidationValue: 100, twrrIndex: 100 }]),
      null,
    );
    assert.equal(
      finance.periodReturnPct([
        { liquidationValue: 100, twrrIndex: 100, asOfDate: "2026-01-01" },
        { liquidationValue: 110, twrrIndex: 100, asOfDate: "2026-01-01" },
      ]),
      null,
      "same calendar day must not invent a period return",
    );
    const ret = finance.periodReturnPct([
      { liquidationValue: 100, twrrIndex: 100, asOfDate: "2026-01-01" },
      { liquidationValue: 110, twrrIndex: 110, asOfDate: "2026-01-02" },
    ]);
    assert.ok(ret != null && Math.abs(ret - 10) < 1e-9);

    assert.equal(
      finance.periodReturnPct([
        { liquidationValue: 0, twrrIndex: 100, asOfDate: "2026-01-01" },
        { liquidationValue: 10, twrrIndex: 100, asOfDate: "2026-01-02" },
      ]),
      null,
    );
  }

  // Weights refuse zero total
  {
    const w = finance.positionWeights([
      { marketValue: 50 },
      { marketValue: 50 },
    ]);
    assert.equal(w[0], 50);
    assert.equal(w[1], 50);
    const z = finance.positionWeights([
      { marketValue: null },
      { marketValue: null },
    ]);
    assert.equal(z[0], null);
  }

  // ─── Sync error classification ──────────────────────────────────
  {
    assert.equal(syncErr.classifySyncFailure("invalid_grant"), "reauth");
    assert.equal(
      syncErr.classifySyncFailure("Schwab re-authorization required"),
      "reauth",
    );
    assert.equal(
      syncErr.classifySyncFailure("contract mismatch on accountNumbers"),
      "contract",
    );
    assert.equal(syncErr.classifySyncFailure("network timeout"), "transient");
    assert.equal(syncErr.classifySyncFailure("429 rate limit"), "transient");
    assert.equal(
      syncErr.connectorStatusAfterSyncFailure("reauth"),
      "needs_reauth",
    );
    // Linked status preserved (not disconnected)
    assert.equal(
      status.isLinkedStatus("needs_reauth"),
      true,
      "reauth must keep connection as linked for last-known-good UX",
    );
    assert.equal(
      status.primaryConnectCta({
        status: "needs_reauth",
        oauthConfigured: true,
      }),
      "reconnect",
    );
    assert.equal(
      status.primaryConnectCta({
        status: "error",
        oauthConfigured: true,
        lastError: "Temporary broker connectivity issue",
      }),
      "retry_sync",
    );
  }

  // ─── Data health banners ────────────────────────────────────────
  {
    const reauth = health.buildDataHealthSummary({
      isDemo: false,
      hasLiveAccounts: true,
      latestAsOf: "2026-07-01",
      connectorStatus: "needs_reauth",
      lastError: "Re-authorization required",
      nlvComplete: true,
      nowMs: Date.parse("2026-08-03T12:00:00Z"),
    });
    assert.equal(reauth.needsReauth, true);
    assert.equal(reauth.showStaleBanner, true);
    assert.equal(reauth.trustLiveNumbers, false);
    assert.equal(reauth.cta, "reconnect");
    assert.ok(reauth.message && /last saved|outdated|reconnect/i.test(reauth.message));

    const fresh = health.buildDataHealthSummary({
      isDemo: false,
      hasLiveAccounts: true,
      latestAsOf: "2026-08-03",
      connectorStatus: "connected",
      lastError: null,
      nlvComplete: true,
      nowMs: Date.parse("2026-08-03T18:00:00Z"),
    });
    assert.equal(fresh.freshness, "live_fresh");
    assert.equal(fresh.trustLiveNumbers, true);
    assert.equal(fresh.showStaleBanner, false);

    const partial = health.buildDataHealthSummary({
      isDemo: false,
      hasLiveAccounts: true,
      latestAsOf: "2026-08-03",
      connectorStatus: "connected",
      lastError: null,
      nlvComplete: false,
      nowMs: Date.parse("2026-08-03T18:00:00Z"),
    });
    assert.equal(partial.showStaleBanner, true);
    assert.ok(partial.message && /incomplete|known/i.test(partial.message));
  }

  // ─── Schwab contract: classic + renamed + drift ─────────────────
  {
    const classic = contract.parseSchwabAccountNumbers([
      { accountNumber: "123", hashValue: "HASH1" },
      { accountNumber: "456", hashValue: "HASH2" },
    ]);
    assert.equal(classic.contractMismatch, false);
    assert.equal(classic.entries.length, 2);

    const renamed = contract.parseSchwabAccountNumbers({
      accounts: [{ account_number: "9", hash_value: "H9" }],
    });
    assert.equal(renamed.entries.length, 1);
    assert.equal(renamed.entries[0].hashValue, "H9");

    const bad = contract.parseSchwabAccountNumbers({ foo: 1 });
    assert.equal(bad.contractMismatch, true);

    const garbageList = contract.parseSchwabAccountNumbers([
      { nonsense: true },
      null,
    ]);
    assert.equal(garbageList.contractMismatch, true);

    // Classic positions
    const acct = contract.parseSchwabAccountPayload(
      {
        securitiesAccount: {
          type: "MARGIN",
          accountNumber: "123",
          currentBalances: {
            liquidationValue: 1000,
            cashBalance: 50,
          },
          positions: [
            {
              instrument: { symbol: "AAPL", assetType: "EQUITY" },
              longQuantity: 10,
              shortQuantity: 0,
              marketValue: 2000,
              averagePrice: 200,
            },
          ],
        },
      },
      { accountNumber: "123", hashValue: "HASH1" },
    );
    assert.ok(acct.account);
    assert.equal(acct.account.liquidationValue, 1000);
    assert.equal(acct.positions.length, 1);
    assert.equal(acct.positions[0].symbol, "AAPL");
    assert.equal(acct.positions[0].quantity, 10);

    // Compact MCP-like quantity field
    const compact = contract.parseSchwabAccountPayload(
      {
        securitiesAccount: {
          type: "CASH",
          currentBalances: { liquidationValue: 500 },
          positions: [
            { symbol: "SGOV", quantity: 100, marketValue: 10000, averagePrice: 100 },
          ],
        },
      },
      { accountNumber: "x", hashValue: "Hx" },
    );
    assert.equal(compact.positions[0].symbol, "SGOV");
    assert.equal(compact.positions[0].quantity, 100);

    // Positions present but unparseable → contract mismatch flag
    const drift = contract.parseSchwabAccountPayload(
      {
        securitiesAccount: {
          currentBalances: { liquidationValue: 1 },
          positions: [{ widget: true, noSymbol: 1 }],
        },
      },
      { accountNumber: "x", hashValue: "Hy" },
    );
    assert.equal(drift.contractMismatch, true);
    assert.equal(drift.positions.length, 0);

    // Missing NLV still yields account identity (last-known path can keep shell)
    const noBal = contract.parseSchwabAccountPayload(
      { securitiesAccount: { type: "MARGIN" } },
      { accountNumber: "1", hashValue: "Hz" },
    );
    assert.ok(noBal.account);
    assert.equal(noBal.account.liquidationValue, null);
    assert.ok(noBal.account.dataQuality < 100);
  }

  // ─── Integration: failed sync keeps last-known holdings ─────────
  {
    const { ensureDbReady, getSql } = await vite.ssrLoadModule("/src/lib/db.ts");
    const { ensurePersonalTenant } = await vite.ssrLoadModule(
      "/src/lib/portfolio/tenant.server.ts",
    );
    const { sealConnectorSecret } = await vite.ssrLoadModule(
      "/src/lib/portfolio/oauth/secrets.server.ts",
    );
    const { pullAndIngestBroker } = await vite.ssrLoadModule(
      "/src/lib/portfolio/brokers/sync.server.ts",
    );
    const { getDashboardPayload } = await vite.ssrLoadModule(
      "/src/lib/portfolio/service.server.ts",
    );
    const { newId } = await vite.ssrLoadModule("/src/lib/security/ids.ts");

    await ensureDbReady();
    const sql = await getSql();
    const tenant = await ensurePersonalTenant("resilience-user");

    // Seed connector + last-known good account/positions manually
    const connId = newId("conn");
    await sql`
      insert into connectors (id, tenant_id, broker, mode, status, auth_kind)
      values (${connId}, ${tenant.id}, ${"schwab"}, ${"direct_oauth"}, ${"connected"}, ${"direct_oauth"})
      on conflict (tenant_id, broker) do update set status = ${"connected"}, last_error = null
    `;
    const crows = await sql`select id from connectors where tenant_id = ${tenant.id} and broker = ${"schwab"}`;
    const cid = crows[0].id;
    await sql`
      insert into connector_secrets (connector_id, tenant_id, ciphertext, key_version)
      values (
        ${cid}, ${tenant.id},
        ${sealConnectorSecret({
          kind: "direct_oauth",
          broker: "schwab",
          access_token: "stale",
          refresh_token: "bad-refresh",
          expires_at: Date.now() - 60_000,
          client_id: "test",
        })},
        ${1}
      )
      on conflict (connector_id) do update set ciphertext = excluded.ciphertext
    `;

    const acctId = newId("acct");
    await sql`
      insert into broker_accounts (
        id, tenant_id, broker, account_key, account_mask, display_name,
        currency, fund_symbol, is_demo
      ) values (
        ${acctId}, ${tenant.id}, ${"schwab"}, ${"reskey1"}, ${"…999"},
        ${"Schwab Resilience"}, ${"USD"}, ${"FUND:schwab:reskey1"}, ${false}
      )
      on conflict do nothing
    `;
    // Resolve actual id if conflict
    const arows = await sql`
      select id from broker_accounts
      where tenant_id = ${tenant.id} and broker = ${"schwab"} and account_key = ${"reskey1"}
    `;
    const aid = arows[0]?.id ?? acctId;
    await sql`
      insert into gt_fund_equity_snapshots (
        tenant_id, account_id, as_of_date, liquidation_value, cash, source, data_quality
      ) values (
        ${tenant.id}, ${aid}, ${"2026-07-15"}::date, ${250000}, ${1000}, ${"schwab"}, ${100}
      )
      on conflict do nothing
    `;
    await sql`
      insert into gt_account_positions (
        tenant_id, account_id, as_of_date, symbol, quantity, market_value,
        price, asset_type, currency, source
      ) values (
        ${tenant.id}, ${aid}, ${"2026-07-15"}::date, ${"TSLA"}, ${10}, ${3000},
        ${300}, ${"equity"}, ${"USD"}, ${"live"}
      )
      on conflict do nothing
    `;

    // Mock refresh/portfolio to fail with reauth
    globalThis.fetch = async (input) => {
      const url = String(input);
      if (url.includes("/oauth/token")) {
        return new Response(JSON.stringify({ error: "invalid_grant" }), {
          status: 400,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response("blocked", { status: 500 });
    };

    let threw = false;
    try {
      await pullAndIngestBroker({ tenantId: tenant.id, broker: "schwab" });
    } catch {
      threw = true;
    }
    assert.equal(threw, true);

    // Secrets + holdings still present
    const secrets = await sql`
      select 1 from connector_secrets where connector_id = ${cid} and tenant_id = ${tenant.id}
    `;
    assert.equal(secrets.length, 1, "tokens must remain sealed after reauth fail");

    const pos = await sql`
      select symbol, market_value from gt_account_positions
      where tenant_id = ${tenant.id} and account_id = ${aid} and symbol = ${"TSLA"}
    `;
    assert.equal(pos.length, 1);
    assert.equal(Number(pos[0].market_value), 3000);

    const snaps = await sql`
      select liquidation_value from gt_fund_equity_snapshots
      where tenant_id = ${tenant.id} and account_id = ${aid}
    `;
    assert.ok(snaps.some((s) => Number(s.liquidation_value) === 250000));

    const conn = await sql`
      select status, last_error from connectors
      where tenant_id = ${tenant.id} and broker = ${"schwab"}
    `;
    assert.equal(conn[0].status, "needs_reauth");
    assert.ok(conn[0].last_error);

    const dash = await getDashboardPayload(tenant.id, {
      id: tenant.id,
      name: tenant.name,
      slug: tenant.slug,
      plan: tenant.plan,
    });
    assert.equal(dash.dataHealth.needsReauth, true);
    assert.equal(dash.dataHealth.showStaleBanner, true);
    assert.equal(dash.workspace.isDemo, false);
    // Last known NLV still surfaces — not wiped to demo or zero
    const live = dash.accounts.filter((a) => !a.isDemo);
    assert.ok(live.length >= 1);
    assert.ok(live.some((a) => a.latestNlv === 250000));
    assert.ok(
      dash.positions.some((p) => p.symbol === "TSLA") ||
        dash.accounts.some((a) => a.id === aid),
    );
  }

  // Contract mismatch must not wipe via empty successful write path
  {
    const assembled = contract.assembleSchwabPortfolio({
      accountNumbersRaw: { broken: true },
      accountPayloads: [],
    });
    assert.equal(assembled.contractMismatch, true);
    assert.equal(assembled.hasUsableAccounts, false);
  }


  // positions vs NLV divergence — never silent on material gap
  {
    const check = finance.positionsVsNlvCheck([100, 100], 1000, { tolerancePct: 25 });
    assert.equal(check.ok, false);
    assert.equal(check.reason, "positions_nlv_divergence");
    const ok = finance.positionsVsNlvCheck([500, 500], 1000, { tolerancePct: 25 });
    assert.equal(ok.ok, true);
    const missingNlv = finance.positionsVsNlvCheck([1], null);
    assert.equal(missingNlv.reason, "account_nlv_unknown");
  }

  // daily return / TWRR chain — null in → null out
  {
    const dr = finance.dailyReturnFromNlv(100, 110);
    assert.ok(dr != null && Math.abs(dr - 0.1) < 1e-12);
    assert.equal(finance.dailyReturnFromNlv(null, 110), null);
    assert.equal(finance.dailyReturnFromNlv(0, 110), null);
    const tw = finance.nextTwrrIndex(100, 0.1);
    assert.ok(tw != null && Math.abs(tw - 110) < 1e-9);
    assert.equal(finance.nextTwrrIndex(null, 0.1), null);
    assert.equal(finance.nextTwrrIndex(100, null), 100);
  }

  console.log("ok: broker resilience (math + health + contract + reauth keep LKG)");
} finally {
  globalThis.fetch = originalFetch;
  await vite.close();
}
