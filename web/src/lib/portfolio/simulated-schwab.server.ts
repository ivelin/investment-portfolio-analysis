/**
 * Simulated Schwab portfolio for preview / local testing.
 * Writes as live (is_demo=false) so the dashboard switches off sample data.
 * Distinct symbols from demo (SGOV/TSLA/… not VOO/AAPL).
 * Never touches real broker APIs.
 */
import { createHash } from "node:crypto";
import { getSql } from "@/lib/db";
import { newId } from "@/lib/security/ids";
import { SIMULATED_SCHWAB_SYMBOLS } from "./dashboard-selection";

const SIM_SOURCE = "simulated";
export const SIMULATED_CONNECTOR_MODE = "simulated";

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function accountKey(label: string): string {
  return createHash("sha256")
    .update(`sim:schwab:${label}`)
    .digest("hex")
    .slice(0, 24);
}

type SimAccount = {
  label: string;
  mask: string;
  type: string;
  nlv: number;
  cash: number;
  positions: Array<{
    symbol: (typeof SIMULATED_SCHWAB_SYMBOLS)[number];
    qty: number;
    price: number;
    assetType: string;
  }>;
};

/** Fixed, recognizable simulated Schwab multi-account book. */
export const SIMULATED_SCHWAB_ACCOUNTS: readonly SimAccount[] = [
  {
    label: "Schwab Individual",
    mask: "…482",
    type: "MARGIN",
    nlv: 842_150.25,
    cash: 12_400,
    positions: [
      { symbol: "SGOV", qty: 3200, price: 100.12, assetType: "etf" },
      { symbol: "TSLA", qty: 180, price: 248.5, assetType: "equity" },
      { symbol: "SCHD", qty: 900, price: 82.4, assetType: "etf" },
      { symbol: "VXUS", qty: 1100, price: 61.2, assetType: "etf" },
    ],
  },
  {
    label: "Schwab IRA",
    mask: "…917",
    type: "IRA",
    nlv: 615_430.8,
    cash: 8_200,
    positions: [
      { symbol: "SGOV", qty: 2100, price: 100.12, assetType: "etf" },
      { symbol: "IBIT", qty: 4200, price: 54.8, assetType: "etf" },
      { symbol: "BND", qty: 1500, price: 72.1, assetType: "etf" },
      { symbol: "SCHD", qty: 600, price: 82.4, assetType: "etf" },
    ],
  },
  {
    label: "Schwab Trust",
    mask: "…305",
    type: "TRUST",
    nlv: 372_880.4,
    cash: 21_050,
    positions: [
      { symbol: "SGOV", qty: 1500, price: 100.12, assetType: "etf" },
      { symbol: "TSLA", qty: 40, price: 248.5, assetType: "equity" },
      { symbol: "VXUS", qty: 800, price: 61.2, assetType: "etf" },
    ],
  },
] as const;

export function simulatedSchwabTotalNlv(): number {
  return SIMULATED_SCHWAB_ACCOUNTS.reduce((s, a) => s + a.nlv, 0);
}

export async function hasSimulatedSchwab(tenantId: string): Promise<boolean> {
  const sql = await getSql();
  const rows = await sql`
    select 1 from broker_accounts
    where tenant_id = ${tenantId}
      and broker = ${"schwab"}
      and is_demo = false
      and account_key like ${"sim_%"}
    limit 1
  `;
  return Boolean(rows[0]);
}

async function hasLiveSchwabOAuth(tenantId: string): Promise<boolean> {
  const sql = await getSql();
  const rows = await sql`
    select 1
    from connectors c
    join connector_secrets s
      on s.connector_id = c.id and s.tenant_id = c.tenant_id
    where c.tenant_id = ${tenantId}
      and c.broker = ${"schwab"}
      and c.mode is distinct from ${SIMULATED_CONNECTOR_MODE}
      and c.status in (${"connected"}, ${"error"}, ${"pending_oauth"})
    limit 1
  `;
  return Boolean(rows[0]);
}

export async function clearSimulatedSchwab(tenantId: string): Promise<void> {
  const sql = await getSql();
  const accts = await sql<{ id: string }>`
    select id from broker_accounts
    where tenant_id = ${tenantId}
      and broker = ${"schwab"}
      and account_key like ${"sim_%"}
  `;
  for (const a of accts) {
    await sql`delete from gt_account_positions where tenant_id = ${tenantId} and account_id = ${a.id}`;
    await sql`delete from fund_daily where tenant_id = ${tenantId} and account_id = ${a.id}`;
    await sql`delete from gt_fund_equity_snapshots where tenant_id = ${tenantId} and account_id = ${a.id}`;
  }
  await sql`
    delete from broker_accounts
    where tenant_id = ${tenantId}
      and broker = ${"schwab"}
      and account_key like ${"sim_%"}
  `;
  await sql`
    delete from connector_secrets
    where tenant_id = ${tenantId}
      and connector_id in (
        select id from connectors
        where tenant_id = ${tenantId}
          and broker = ${"schwab"}
          and mode = ${SIMULATED_CONNECTOR_MODE}
      )
  `;
  await sql`
    delete from connectors
    where tenant_id = ${tenantId}
      and broker = ${"schwab"}
      and mode = ${SIMULATED_CONNECTOR_MODE}
  `;
}

/**
 * Import simulated Schwab balances + holdings as live (non-demo) data.
 * Idempotent: clears prior simulation first.
 * Refuses if a real Schwab OAuth link exists (won't overwrite tokens).
 */
export async function seedSimulatedSchwab(tenantId: string): Promise<{
  accountCount: number;
  positionCount: number;
  totalNlv: number;
}> {
  if (await hasLiveSchwabOAuth(tenantId)) {
    throw new Error(
      "A real Schwab connection already exists. Disconnect it first, or use Sync for live data.",
    );
  }
  await clearSimulatedSchwab(tenantId);
  const sql = await getSql();
  const today = new Date();
  const asOf = isoDate(today);
  let positionCount = 0;

  const connId = newId("conn");
  await sql`
    insert into connectors (
      id, tenant_id, broker, mode, status, auth_kind, last_sync_at, last_error
    ) values (
      ${connId}, ${tenantId}, ${"schwab"}, ${SIMULATED_CONNECTOR_MODE}, ${"connected"},
      ${"simulated_import"}, now(), null
    )
    on conflict (tenant_id, broker) do update set
      mode = ${SIMULATED_CONNECTOR_MODE},
      status = ${"connected"},
      auth_kind = ${"simulated_import"},
      last_sync_at = now(),
      last_error = null,
      updated_at = now()
  `;

  for (const acct of SIMULATED_SCHWAB_ACCOUNTS) {
    const key = `sim_${accountKey(acct.label)}`;
    const accountId = newId("acct");
    const fundSymbol = `FUND:schwab:${key.slice(0, 10)}`;

    await sql`
      insert into broker_accounts (
        id, tenant_id, broker, account_key, account_mask, display_name,
        currency, fund_symbol, is_demo
      ) values (
        ${accountId}, ${tenantId}, ${"schwab"}, ${key}, ${acct.mask},
        ${`${acct.label} (sim)`}, ${"USD"}, ${fundSymbol}, ${false}
      )
      on conflict (tenant_id, broker, account_key) do update set
        display_name = excluded.display_name,
        account_mask = excluded.account_mask,
        is_demo = ${false},
        updated_at = now()
    `;

    const resolved = await sql<{ id: string }>`
      select id from broker_accounts
      where tenant_id = ${tenantId} and broker = ${"schwab"} and account_key = ${key}
      limit 1
    `;
    const id = resolved[0]?.id ?? accountId;

    let nlv = acct.nlv * 0.94;
    let index = 100;
    for (let i = 44; i >= 0; i -= 1) {
      const d = new Date(today);
      d.setUTCDate(d.getUTCDate() - i);
      const day = isoDate(d);
      const ret = i === 44 ? 0 : (Math.sin(i / 5) + Math.cos(i / 11)) * 0.0015;
      if (i < 44) {
        nlv = nlv * (1 + ret);
        index = index * (1 + ret);
      }
      if (i === 0) nlv = acct.nlv;
      await sql`
        insert into gt_fund_equity_snapshots (
          tenant_id, account_id, as_of_date, liquidation_value, cash, source, data_quality
        ) values (
          ${tenantId}, ${id}, ${day}::date, ${nlv}, ${acct.cash}, ${SIM_SOURCE}, ${100}
        )
        on conflict (tenant_id, account_id, as_of_date, source) do update set
          liquidation_value = excluded.liquidation_value,
          cash = excluded.cash,
          ingested_at = now()
      `;
      await sql`
        insert into fund_daily (
          tenant_id, account_id, fund_symbol, as_of_date, liquidation_value,
          external_cf, daily_return, twrr_index, data_quality
        ) values (
          ${tenantId}, ${id}, ${fundSymbol}, ${day}::date, ${nlv},
          ${0}, ${ret}, ${index}, ${100}
        )
        on conflict (tenant_id, fund_symbol, as_of_date) do update set
          liquidation_value = excluded.liquidation_value,
          account_id = excluded.account_id,
          daily_return = excluded.daily_return,
          twrr_index = excluded.twrr_index,
          calc_timestamp = now()
      `;
    }

    for (const p of acct.positions) {
      const mv = p.qty * p.price;
      positionCount += 1;
      await sql`
        insert into gt_account_positions (
          tenant_id, account_id, as_of_date, symbol, quantity, market_value,
          price, asset_type, currency, source
        ) values (
          ${tenantId}, ${id}, ${asOf}::date, ${p.symbol}, ${p.qty}, ${mv},
          ${p.price}, ${p.assetType}, ${"USD"}, ${SIM_SOURCE}
        )
        on conflict (tenant_id, account_id, as_of_date, symbol, source) do update set
          quantity = excluded.quantity,
          market_value = excluded.market_value,
          price = excluded.price,
          ingested_at = now()
      `;
    }
  }

  return {
    accountCount: SIMULATED_SCHWAB_ACCOUNTS.length,
    positionCount,
    totalNlv: simulatedSchwabTotalNlv(),
  };
}
