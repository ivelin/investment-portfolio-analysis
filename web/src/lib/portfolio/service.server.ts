import { getSql } from "@/lib/db";
import { newId } from "@/lib/security/ids";
import {
  isSimulatedAccountRow,
  pickPrimaryAccount,
  resolveDashboardDataMode,
  workspaceIsDemoOnly,
} from "./dashboard-selection";
import type {
  AccountSummary,
  DashboardDataMode,
  DashboardPayload,
  FundSeriesPoint,
  PositionRow,
  WorkspaceSummary,
} from "./types";

const DEMO_SYMBOLS = [
  { symbol: "AAPL", qty: 40, price: 190, type: "equity" },
  { symbol: "MSFT", qty: 25, price: 420, type: "equity" },
  { symbol: "NVDA", qty: 15, price: 110, type: "equity" },
  { symbol: "VOO", qty: 30, price: 500, type: "etf" },
  { symbol: "CASH", qty: 12500, price: 1, type: "cash" },
] as const;

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function periodReturnPct(series: FundSeriesPoint[]): number | null {
  if (series.length < 2) return null;
  const firstNlv = series[0].liquidationValue;
  const lastNlv = series[series.length - 1].liquidationValue;
  if (!(firstNlv > 0) || !Number.isFinite(lastNlv)) return null;
  const firstIdx = series[0].twrrIndex;
  const lastIdx = series[series.length - 1].twrrIndex;
  if (firstIdx > 0 && lastIdx > 0 && Math.abs(lastIdx - firstIdx) > 1e-9) {
    return (lastIdx / firstIdx - 1) * 100;
  }
  return (lastNlv / firstNlv - 1) * 100;
}

/** Seed a labeled synthetic demo fund for a brand-new tenant. */
export async function seedDemoPortfolio(tenantId: string): Promise<void> {
  const sql = await getSql();
  const existing = await sql`
    select id from broker_accounts
    where tenant_id = ${tenantId} and is_demo = true
    limit 1
  `;
  if (existing[0]) return;

  const accountId = newId("acct");
  const accountKey = newId("key").slice(0, 16);
  const fundSymbol = `FUND:synthetic:${accountKey}`;

  await sql`
    insert into broker_accounts (
      id, tenant_id, broker, account_key, account_mask, display_name,
      currency, fund_symbol, is_demo
    ) values (
      ${accountId}, ${tenantId}, ${"synthetic"}, ${accountKey}, ${"…001"},
      ${"Sample growth fund"}, ${"USD"}, ${fundSymbol}, ${true}
    )
  `;

  const today = new Date();
  let nlv = 100_000;
  let index = 100;
  for (let i = 90; i >= 0; i -= 1) {
    const d = new Date(today);
    d.setUTCDate(d.getUTCDate() - i);
    const asOf = isoDate(d);
    const ret = (Math.sin(i / 7) + Math.cos(i / 13)) * 0.002;
    if (i < 90) {
      nlv = nlv * (1 + ret);
      index = index * (1 + ret);
    }
    await sql`
      insert into gt_fund_equity_snapshots (
        tenant_id, account_id, as_of_date, liquidation_value, cash, source, data_quality
      ) values (
        ${tenantId}, ${accountId}, ${asOf}::date, ${nlv}, ${12_500}, ${"demo"}, ${100}
      )
      on conflict do nothing
    `;
    await sql`
      insert into fund_daily (
        tenant_id, account_id, fund_symbol, as_of_date, liquidation_value,
        external_cf, daily_return, twrr_index, data_quality
      ) values (
        ${tenantId}, ${accountId}, ${fundSymbol}, ${asOf}::date, ${nlv},
        ${0}, ${ret}, ${index}, ${100}
      )
      on conflict do nothing
    `;
  }

  const asOf = isoDate(today);
  for (const p of DEMO_SYMBOLS) {
    const mv = p.qty * p.price;
    await sql`
      insert into gt_account_positions (
        tenant_id, account_id, as_of_date, symbol, quantity, market_value,
        price, asset_type, currency, source
      ) values (
        ${tenantId}, ${accountId}, ${asOf}::date, ${p.symbol}, ${p.qty}, ${mv},
        ${p.price}, ${p.type}, ${"USD"}, ${"demo"}
      )
      on conflict do nothing
    `;
  }
}

export async function listAccounts(tenantId: string): Promise<AccountSummary[]> {
  const sql = await getSql();
  const rows = await sql<{
    id: string;
    broker: string;
    display_name: string;
    account_mask: string;
    account_key: string;
    fund_symbol: string;
    is_demo: boolean;
    currency: string;
    latest_nlv: number | null;
    latest_as_of: string | null;
  }>`
    select
      a.id,
      a.broker,
      a.display_name,
      a.account_mask,
      a.account_key,
      a.fund_symbol,
      a.is_demo,
      a.currency,
      (
        select s.liquidation_value
        from gt_fund_equity_snapshots s
        where s.tenant_id = a.tenant_id and s.account_id = a.id
        order by s.as_of_date desc
        limit 1
      ) as latest_nlv,
      (
        select s.as_of_date::text
        from gt_fund_equity_snapshots s
        where s.tenant_id = a.tenant_id and s.account_id = a.id
        order by s.as_of_date desc
        limit 1
      ) as latest_as_of
    from broker_accounts a
    where a.tenant_id = ${tenantId}
    order by a.is_demo asc,
      coalesce(
        (
          select s.liquidation_value
          from gt_fund_equity_snapshots s
          where s.tenant_id = a.tenant_id and s.account_id = a.id
          order by s.as_of_date desc
          limit 1
        ),
        0
      ) desc,
      a.created_at asc
  `;
  return rows.map((r) => ({
    id: r.id,
    broker: r.broker,
    displayName: r.display_name,
    accountMask: r.account_mask,
    fundSymbol: r.fund_symbol,
    isDemo: Boolean(r.is_demo),
    isSimulated: isSimulatedAccountRow({
      accountKey: r.account_key,
      displayName: r.display_name,
    }),
    currency: r.currency,
    latestNlv: r.latest_nlv == null ? null : Number(r.latest_nlv),
    latestAsOf: r.latest_as_of,
  }));
}

async function listConnectorModes(tenantId: string): Promise<string[]> {
  const sql = await getSql();
  const rows = await sql<{ mode: string }>`
    select mode from connectors
    where tenant_id = ${tenantId}
      and status in (${"connected"}, ${"error"}, ${"pending_oauth"})
  `;
  return rows.map((r) => r.mode).filter(Boolean);
}

export async function getPositions(
  tenantId: string,
  accountId: string,
): Promise<PositionRow[]> {
  const sql = await getSql();
  const rows = await sql<{
    symbol: string;
    asset_type: string | null;
    quantity: number;
    price: number | null;
    market_value: number | null;
  }>`
    select symbol, asset_type, quantity, price, market_value
    from gt_account_positions
    where tenant_id = ${tenantId}
      and account_id = ${accountId}
      and as_of_date = (
        select max(as_of_date) from gt_account_positions
        where tenant_id = ${tenantId} and account_id = ${accountId}
      )
    order by market_value desc nulls last, symbol
  `;
  const total = rows.reduce((s, r) => s + (Number(r.market_value) || 0), 0);
  return rows.map((r) => {
    const mv = r.market_value == null ? null : Number(r.market_value);
    return {
      symbol: r.symbol,
      assetType: r.asset_type,
      quantity: Number(r.quantity),
      price: r.price == null ? null : Number(r.price),
      marketValue: mv,
      weightPct: mv != null && total > 0 ? (mv / total) * 100 : null,
    };
  });
}

export async function getFundSeries(
  tenantId: string,
  accountId: string,
  limit?: number,
): Promise<FundSeriesPoint[]> {
  const sql = await getSql();
  const rows = await sql<{
    as_of_date: string;
    liquidation_value: number;
    twrr_index: number;
    daily_return: number | null;
  }>`
    select as_of_date::text as as_of_date, liquidation_value, twrr_index, daily_return
    from fund_daily
    where tenant_id = ${tenantId} and account_id = ${accountId}
    order by as_of_date asc
  `;
  if (rows.length === 0) {
    const snaps = await sql<{
      as_of_date: string;
      liquidation_value: number;
    }>`
      select as_of_date::text as as_of_date, liquidation_value
      from gt_fund_equity_snapshots
      where tenant_id = ${tenantId} and account_id = ${accountId}
      order by as_of_date asc
    `;
    return snaps.map((r) => ({
      asOfDate: r.as_of_date,
      liquidationValue: Number(r.liquidation_value),
      twrrIndex: 100,
      dailyReturn: null,
    }));
  }
  const mapped = rows.map((r) => ({
    asOfDate: r.as_of_date,
    liquidationValue: Number(r.liquidation_value),
    twrrIndex: Number(r.twrr_index),
    dailyReturn: r.daily_return == null ? null : Number(r.daily_return),
  }));
  if (limit != null && limit > 0 && mapped.length > limit) {
    return mapped.slice(mapped.length - limit);
  }
  return mapped;
}

export async function resolveAccountId(
  tenantId: string,
  accountId: string | null,
): Promise<string | null> {
  const accounts = await listAccounts(tenantId);
  if (accountId) {
    return accounts.some((a) => a.id === accountId) ? accountId : null;
  }
  return pickPrimaryAccount(accounts)?.id ?? null;
}

export async function getConnectorStatuses(tenantId: string) {
  const { listConnectors } = await import("./connectors.server");
  return listConnectors(tenantId);
}

function computeDataMode(
  accounts: AccountSummary[],
  connectorModes: string[],
): DashboardDataMode {
  return resolveDashboardDataMode({ accounts, connectorModes });
}

export async function getWorkspaceSummary(
  tenantId: string,
  tenant: { id: string; name: string; slug: string; plan: string },
  primaryAccountId?: string | null,
): Promise<WorkspaceSummary> {
  const accounts = await listAccounts(tenantId);
  const modes = await listConnectorModes(tenantId);
  const dataMode = computeDataMode(accounts, modes);
  const live = accounts.filter((a) => !a.isDemo && !a.isSimulated);
  const anyLive = accounts.filter((a) => !a.isDemo);
  const primary = pickPrimaryAccount(accounts, primaryAccountId);
  let twrrPeriodReturnPct: number | null = null;
  if (primary) {
    const series = await getFundSeries(tenantId, primary.id);
    twrrPeriodReturnPct = periodReturnPct(series);
  }
  const sumPool = live.length > 0 ? live : anyLive;
  const latestNlv =
    sumPool.length > 0
      ? sumPool.reduce((s, a) => s + (a.latestNlv ?? 0), 0)
      : (primary?.latestNlv ?? null);
  return {
    id: tenant.id,
    name: tenant.name,
    slug: tenant.slug,
    plan: tenant.plan,
    latestNlv,
    latestAsOf: primary?.latestAsOf ?? null,
    twrrPeriodReturnPct,
    isDemo: workspaceIsDemoOnly(accounts),
    accountCount: accounts.length,
    dataMode,
  };
}

export type AccountPortfolio = {
  accountId: string;
  series: FundSeriesPoint[];
  positions: PositionRow[];
  periodReturnPct: number | null;
  latestNlv: number | null;
  latestAsOf: string | null;
};

/** Chart + positions for one account (tenant-scoped). */
export async function getAccountPortfolio(
  tenantId: string,
  accountId: string,
): Promise<AccountPortfolio | null> {
  const accounts = await listAccounts(tenantId);
  const acct = accounts.find((a) => a.id === accountId);
  if (!acct) return null;
  const series = await getFundSeries(tenantId, accountId);
  const positions = await getPositions(tenantId, accountId);
  return {
    accountId,
    series,
    positions,
    periodReturnPct: periodReturnPct(series),
    latestNlv: acct.latestNlv,
    latestAsOf: acct.latestAsOf,
  };
}

export async function getDashboardPayload(
  tenantId: string,
  tenant: { id: string; name: string; slug: string; plan: string },
  preferredAccountId?: string | null,
): Promise<DashboardPayload> {
  const accounts = await listAccounts(tenantId);
  const modes = await listConnectorModes(tenantId);
  const dataMode = computeDataMode(accounts, modes);
  // Prefer linked/live; never default chart/positions to sample when live exists.
  const primary = pickPrimaryAccount(accounts, preferredAccountId);
  const series = primary ? await getFundSeries(tenantId, primary.id) : [];
  const positions = primary ? await getPositions(tenantId, primary.id) : [];
  const workspace = await getWorkspaceSummary(tenantId, tenant, primary?.id);
  workspace.dataMode = dataMode;
  if (primary) {
    workspace.twrrPeriodReturnPct = periodReturnPct(series);
    workspace.latestAsOf = primary.latestAsOf;
  }
  return {
    workspace,
    accounts,
    series,
    positions,
    selectedAccountId: primary?.id ?? null,
    dataMode,
  };
}
