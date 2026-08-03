import { createHash } from "node:crypto";
import { getSql } from "@/lib/db";
import { newId } from "@/lib/security/ids";
import {
  openConnectorSecret,
  sealConnectorSecret,
} from "../oauth/secrets.server";
import {
  fetchSchwabPortfolio,
  refreshSchwabToken,
} from "../oauth/schwab.server";
import { refreshMcpToken } from "../oauth/mcp-oauth.server";
import {
  dailyReturnFromNlv,
  finiteNumber,
  nextTwrrIndex,
} from "../finance-math";
import { isPersistableNlv } from "./schwab-contract";
import type { BrokerId } from "./catalog";
import { assertBrokerConnectorsReadOnly } from "./read-only-policy";
import {
  classifySyncFailure,
  connectorStatusAfterSyncFailure,
  isReauthErrorMessage,
  userMessageForSyncFailure,
} from "./sync-errors";

export {
  isReauthErrorMessage,
  classifySyncFailure,
  connectorStatusAfterSyncFailure,
  userMessageForSyncFailure,
} from "./sync-errors";

function isoDate(d = new Date()): string {
  return d.toISOString().slice(0, 10);
}

function accountKeyFromExternal(broker: string, external: string): string {
  return createHash("sha256")
    .update(`${broker}:${external}`)
    .digest("hex")
    .slice(0, 24);
}

function maskAccount(raw: string): string {
  const digits = raw.replace(/\D/g, "");
  if (digits.length >= 3) return `…${digits.slice(-3)}`;
  if (raw.length >= 3) return `…${raw.slice(-3)}`;
  return "…";
}

async function loadTokens(
  tenantId: string,
  broker: BrokerId,
): Promise<{ connectorId: string; tokens: Record<string, unknown> } | null> {
  const sql = await getSql();
  const rows = await sql<{
    connector_id: string;
    ciphertext: string;
  }>`
    select c.id as connector_id, s.ciphertext
    from connectors c
    join connector_secrets s on s.connector_id = c.id and s.tenant_id = c.tenant_id
    where c.tenant_id = ${tenantId}
      and c.broker = ${broker}
      and c.status in (${"connected"}, ${"error"}, ${"needs_reauth"}, ${"pending_oauth"})
    limit 1
  `;
  const row = rows[0];
  if (!row) return null;
  return {
    connectorId: row.connector_id,
    tokens: openConnectorSecret(row.ciphertext),
  };
}

async function saveTokens(
  tenantId: string,
  connectorId: string,
  tokens: Record<string, unknown>,
): Promise<void> {
  const sql = await getSql();
  await sql`
    update connector_secrets set
      ciphertext = ${sealConnectorSecret(tokens)},
      updated_at = now()
    where connector_id = ${connectorId} and tenant_id = ${tenantId}
  `;
}

async function withFreshTokens(args: {
  tenantId: string;
  broker: BrokerId;
  connectorId: string;
  tokens: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  const { tokens } = args;
  const expiresAt = Number(tokens.expires_at ?? 0);
  const skewMs = 60_000;
  if (expiresAt && Date.now() < expiresAt - skewMs) {
    return tokens;
  }

  if (args.broker === "schwab") {
    const refresh = String(tokens.refresh_token || "");
    if (!refresh) throw new Error("Schwab re-authorization required");
    const next = await refreshSchwabToken({
      refreshToken: refresh,
      clientId: String(tokens.client_id || "") || undefined,
    });
    const merged = { ...tokens, ...next };
    await saveTokens(args.tenantId, args.connectorId, merged);
    return merged;
  }

  if (args.broker === "robinhood") {
    const refresh = String(tokens.refresh_token || "");
    if (!refresh) throw new Error("Re-authorization required");
    const next = await refreshMcpToken({
      broker: args.broker,
      refreshToken: refresh,
      clientId: String(tokens.client_id || ""),
      tokenEndpoint: String(tokens.token_endpoint || ""),
      resource: (tokens.resource as string) || null,
    });
    const merged = { ...tokens, ...next };
    await saveTokens(args.tenantId, args.connectorId, merged);
    return merged;
  }

  return tokens;
}

async function upsertAccount(args: {
  tenantId: string;
  broker: BrokerId;
  externalKey: string;
  displayName: string;
  currency?: string;
  nlv?: number | null;
  cash?: number | null;
  dataQuality?: number;
}): Promise<string> {
  const sql = await getSql();
  const key = accountKeyFromExternal(args.broker, args.externalKey);
  const existing = await sql<{ id: string }>`
    select id from broker_accounts
    where tenant_id = ${args.tenantId}
      and broker = ${args.broker}
      and account_key = ${key}
    limit 1
  `;
  const accountId = existing[0]?.id ?? newId("acct");
  const fundSymbol = `FUND:${args.broker}:${key.slice(0, 8)}`;
  const mask = maskAccount(args.externalKey);

  if (!existing[0]) {
    await sql`
      insert into broker_accounts (
        id, tenant_id, broker, account_key, account_mask, display_name,
        currency, fund_symbol, is_demo
      ) values (
        ${accountId}, ${args.tenantId}, ${args.broker}, ${key}, ${mask},
        ${args.displayName}, ${args.currency ?? "USD"}, ${fundSymbol}, ${false}
      )
    `;
  } else {
    await sql`
      update broker_accounts set
        display_name = ${args.displayName},
        account_mask = ${mask},
        updated_at = now()
      where id = ${accountId} and tenant_id = ${args.tenantId}
    `;
  }

  // Only write NLV when finite — never invent 0 from missing balances.
  if (isPersistableNlv(args.nlv)) {
    const asOf = isoDate();
    const quality =
      args.dataQuality != null && Number.isFinite(args.dataQuality)
        ? Math.max(0, Math.min(100, Math.round(args.dataQuality)))
        : 100;

    const prev = await sql<{
      liquidation_value: number;
      twrr_index: number;
      as_of_date: string;
    }>`
      select liquidation_value, twrr_index, as_of_date::text as as_of_date
      from fund_daily
      where tenant_id = ${args.tenantId} and fund_symbol = ${fundSymbol}
      order by as_of_date desc
      limit 1
    `;
    let dailyRet: number | null = null;
    let twrr = 100;
    if (prev[0]) {
      if (prev[0].as_of_date === asOf) {
        const dayBefore = await sql<{
          liquidation_value: number;
          twrr_index: number;
        }>`
          select liquidation_value, twrr_index
          from fund_daily
          where tenant_id = ${args.tenantId}
            and fund_symbol = ${fundSymbol}
            and as_of_date < ${asOf}::date
          order by as_of_date desc
          limit 1
        `;
        if (dayBefore[0]) {
          dailyRet = dailyReturnFromNlv(
            dayBefore[0].liquidation_value,
            args.nlv,
          );
          const next = nextTwrrIndex(dayBefore[0].twrr_index, dailyRet);
          twrr = next ?? (finiteNumber(dayBefore[0].twrr_index) ?? 100);
        } else {
          dailyRet = null;
          twrr = finiteNumber(prev[0].twrr_index) ?? 100;
        }
      } else {
        dailyRet = dailyReturnFromNlv(prev[0].liquidation_value, args.nlv);
        const next = nextTwrrIndex(prev[0].twrr_index, dailyRet);
        twrr = next ?? 100;
      }
    }

    await sql`
      insert into gt_fund_equity_snapshots (
        tenant_id, account_id, as_of_date, liquidation_value, cash, source, data_quality
      ) values (
        ${args.tenantId}, ${accountId}, ${asOf}::date, ${args.nlv},
        ${args.cash ?? null}, ${args.broker}, ${quality}
      )
      on conflict (tenant_id, account_id, as_of_date, source) do update set
        liquidation_value = excluded.liquidation_value,
        cash = excluded.cash,
        data_quality = excluded.data_quality,
        ingested_at = now()
    `;
    await sql`
      insert into fund_daily (
        tenant_id, account_id, fund_symbol, as_of_date, liquidation_value,
        external_cf, daily_return, twrr_index, data_quality
      ) values (
        ${args.tenantId}, ${accountId}, ${fundSymbol}, ${asOf}::date, ${args.nlv},
        ${0}, ${dailyRet}, ${twrr}, ${quality}
      )
      on conflict (tenant_id, fund_symbol, as_of_date) do update set
        liquidation_value = excluded.liquidation_value,
        account_id = excluded.account_id,
        daily_return = excluded.daily_return,
        twrr_index = excluded.twrr_index,
        data_quality = excluded.data_quality,
        calc_timestamp = now()
    `;
  }

  return accountId;
}

async function upsertPositions(args: {
  tenantId: string;
  accountId: string;
  broker: BrokerId;
  positions: Array<{
    symbol: string;
    quantity: number;
    marketValue?: number | null;
    price?: number | null;
    assetType?: string | null;
  }>;
}): Promise<void> {
  const sql = await getSql();
  const asOf = isoDate();
  await sql`
    delete from gt_account_positions
    where tenant_id = ${args.tenantId}
      and account_id = ${args.accountId}
      and as_of_date = ${asOf}::date
      and source in (${args.broker}, ${"live"}, ${"csv_import"}, ${"mcp_live"})
  `;
  for (const p of args.positions) {
    const qty = finiteNumber(p.quantity);
    if (!p.symbol || qty == null || qty === 0) continue;
    const mv = finiteNumber(p.marketValue ?? null);
    const price = finiteNumber(p.price ?? null);
    await sql`
      insert into gt_account_positions (
        tenant_id, account_id, as_of_date, symbol, quantity, market_value,
        price, asset_type, currency, source
      ) values (
        ${args.tenantId}, ${args.accountId}, ${asOf}::date, ${p.symbol},
        ${qty}, ${mv}, ${price},
        ${p.assetType ?? null}, ${"USD"}, ${"live"}
      )
      on conflict (tenant_id, account_id, as_of_date, symbol, source) do update set
        quantity = excluded.quantity,
        market_value = excluded.market_value,
        price = excluded.price,
        asset_type = excluded.asset_type,
        ingested_at = now()
    `;
  }
}

/** Read-only Schwab portfolio pull — never places orders; never wipes on failure. */
async function syncSchwab(tenantId: string): Promise<void> {
  assertBrokerConnectorsReadOnly();
  const loaded = await loadTokens(tenantId, "schwab");
  if (!loaded) throw new Error("Schwab not connected");
  const tokens = await withFreshTokens({
    tenantId,
    broker: "schwab",
    connectorId: loaded.connectorId,
    tokens: loaded.tokens,
  });
  const access = String(tokens.access_token || "");
  if (!access) throw new Error("Schwab re-authorization required");

  const portfolio = await fetchSchwabPortfolio(access);

  // Live data wins: drop leftover simulated rows only after a successful pull.
  const { clearSimulatedSchwab } = await import("../simulated-schwab.server");
  await clearSimulatedSchwab(tenantId).catch(() => undefined);

  for (const acct of portfolio.accounts) {
    const externalKey = acct.hashValue || acct.accountNumber;
    const nick = acct.nickname != null ? String(acct.nickname).trim() : "";
    const label = nick
      ? `Schwab ${nick}`
      : `Schwab ${acct.type || "Account"}`;
    const accountId = await upsertAccount({
      tenantId,
      broker: "schwab",
      externalKey,
      displayName: label,
      nlv: acct.liquidationValue ?? null,
      cash: acct.cash ?? null,
      dataQuality: acct.dataQuality,
    });
    const positions = portfolio.positions
      .filter((p) => p.accountHash === acct.hashValue)
      .map((p) => ({
        symbol: p.symbol,
        quantity: p.quantity,
        marketValue: p.marketValue,
        price: p.price,
        assetType: p.assetType,
      }));
    await upsertPositions({
      tenantId,
      accountId,
      broker: "schwab",
      positions,
    });
  }
}

async function syncRobinhood(tenantId: string): Promise<void> {
  assertBrokerConnectorsReadOnly();
  const loaded = await loadTokens(tenantId, "robinhood");
  if (!loaded) throw new Error("Robinhood not connected");
  await withFreshTokens({
    tenantId,
    broker: "robinhood",
    connectorId: loaded.connectorId,
    tokens: loaded.tokens,
  });
}

/**
 * Pull + ingest for a connected broker (tenant-scoped tokens only).
 * **Read-only analysis.** Never places orders or mutates brokerage accounts.
 * On failure: keeps last-known-good holdings; marks connector for reauth/retry.
 */
export async function pullAndIngestBroker(args: {
  tenantId: string;
  broker: BrokerId;
}): Promise<void> {
  assertBrokerConnectorsReadOnly();
  const sql = await getSql();
  try {
    if (args.broker === "schwab") {
      await syncSchwab(args.tenantId);
    } else if (args.broker === "robinhood") {
      await syncRobinhood(args.tenantId);
    }
    await sql`
      update connectors set
        last_sync_at = now(),
        last_error = null,
        status = ${"connected"},
        mode = CASE
          WHEN mode = ${"simulated"} THEN ${"direct_oauth"}
          ELSE mode
        END,
        updated_at = now()
      where tenant_id = ${args.tenantId} and broker = ${args.broker}
    `;
  } catch (err) {
    const raw = err instanceof Error ? err.message : "Sync failed";
    const failure = classifySyncFailure(raw);
    const status = connectorStatusAfterSyncFailure(failure);
    const msg = userMessageForSyncFailure(failure, raw);
    await sql`
      update connectors set
        last_error = ${msg.slice(0, 400)},
        status = ${status},
        updated_at = now()
      where tenant_id = ${args.tenantId} and broker = ${args.broker}
    `;
    // Do NOT delete accounts, positions, or secrets — last-known-good stays.
    throw err;
  }
}
