import { getSql } from "@/lib/db";
import { BROKER_IDS, BROKERS, type BrokerId } from "./brokers/catalog";
import { BROKER_READ_ONLY_PROMISE } from "./brokers/read-only-policy";
import { startBrokerOAuth } from "./oauth.server";
import { schwabOAuthConfigured } from "./oauth/schwab.server";
import { mcpOAuthConfigured } from "./oauth/mcp-oauth.server";
import { pullAndIngestBroker } from "./brokers/sync.server";
import { SIMULATED_CONNECTOR_MODE } from "./simulated-schwab.server";

const DESCRIPTIONS: Record<BrokerId, string> = {
  schwab:
    "Read-only Schwab Trader API — balances and positions for analysis. Never places orders.",
  robinhood:
    "Robinhood MCP OAuth (read-only analysis). We never call trade/order tools.",
  ibkr: "Interactive Brokers MCP when available — read-only analysis only.",
  fidelity: "Live API not available yet — connection will open when ready.",
  synthetic: "Labeled sample fund for demos — not a live broker.",
};

export type ConnectorPublic = {
  broker: BrokerId;
  label: string;
  description: string;
  status: string;
  mode: string;
  oauthConfigured: boolean;
  lastSyncAt: string | null;
  lastError: string | null;
  authKind: string;
  accountCount: number;
  /** True when holdings came from in-app simulated import (not OAuth). */
  isSimulated: boolean;
  readOnly: true;
  readOnlyPromise: string;
};

async function brokerConfigured(broker: BrokerId): Promise<boolean> {
  if (broker === "schwab") return schwabOAuthConfigured();
  if (broker === "robinhood") return mcpOAuthConfigured("robinhood");
  if (broker === "ibkr") return mcpOAuthConfigured("ibkr").catch(() => false);
  if (broker === "synthetic") return true;
  if (BROKERS[broker].authKind === "exports_only") return false;
  return false;
}

export async function listConnectors(
  tenantId: string,
): Promise<ConnectorPublic[]> {
  const sql = await getSql();
  const rows = await sql<{
    broker: string;
    status: string;
    mode: string;
    last_sync_at: string | null;
    last_error: string | null;
    auth_kind: string | null;
  }>`
    select broker, status, mode, last_sync_at::text as last_sync_at, last_error, auth_kind
    from connectors
    where tenant_id = ${tenantId}
  `;
  const byBroker = new Map(rows.map((r) => [r.broker, r]));
  const acctRows = await sql<{ broker: string; n: number }>`
    select broker, count(*)::int as n
    from broker_accounts
    where tenant_id = ${tenantId} and is_demo = false
    group by broker
  `;
  const acctBy = new Map(acctRows.map((r) => [r.broker, Number(r.n)]));

  const out: ConnectorPublic[] = [];
  for (const id of BROKER_IDS) {
    if (id === "synthetic") continue;
    const def = BROKERS[id];
    const row = byBroker.get(id);
    const oauthConfigured = await brokerConfigured(id);
    const isSimulated = row?.mode === SIMULATED_CONNECTOR_MODE;
    out.push({
      broker: id,
      label: def.label,
      description: isSimulated
        ? "Simulated Schwab holdings for preview — not a live OAuth link. Clear anytime."
        : DESCRIPTIONS[id],
      status: row?.status ?? "disconnected",
      mode: row?.mode ?? def.authKind,
      oauthConfigured,
      lastSyncAt: row?.last_sync_at ?? null,
      lastError: row?.last_error ?? null,
      authKind: row?.auth_kind ?? def.authKind,
      accountCount: acctBy.get(id) ?? 0,
      isSimulated,
      readOnly: true,
      readOnlyPromise: BROKER_READ_ONLY_PROMISE,
    });
  }
  return out;
}

export async function connectBroker(args: {
  tenantId: string;
  userId: string;
  broker: BrokerId;
  origin: string;
}): Promise<
  | { kind: "oauth_redirect"; authorizeUrl: string }
  | { kind: "not_configured"; message: string }
> {
  return startBrokerOAuth(args);
}

export async function disconnectBroker(args: {
  tenantId: string;
  broker: BrokerId;
}): Promise<void> {
  const sql = await getSql();
  // If this was a simulation, wipe simulated accounts too.
  const modeRows = await sql<{ mode: string }>`
    select mode from connectors
    where tenant_id = ${args.tenantId} and broker = ${args.broker}
    limit 1
  `;
  if (modeRows[0]?.mode === SIMULATED_CONNECTOR_MODE && args.broker === "schwab") {
    const { clearSimulatedSchwab } = await import("./simulated-schwab.server");
    await clearSimulatedSchwab(args.tenantId);
    return;
  }
  const rows = await sql<{ id: string }>`
    select id from connectors
    where tenant_id = ${args.tenantId} and broker = ${args.broker}
    limit 1
  `;
  const id = rows[0]?.id;
  if (!id) return;
  await sql`delete from connector_secrets where connector_id = ${id} and tenant_id = ${args.tenantId}`;
  await sql`
    update connectors set
      status = ${"disconnected"},
      last_error = null,
      updated_at = now()
    where id = ${id} and tenant_id = ${args.tenantId}
  `;
}

export async function syncBrokers(
  tenantId: string,
  broker?: BrokerId,
): Promise<{ synced: number }> {
  const sql = await getSql();
  const rows = broker
    ? await sql<{ broker: string; mode: string }>`
        select broker, mode from connectors
        where tenant_id = ${tenantId}
          and status in (${"connected"}, ${"error"})
          and broker = ${broker}
      `
    : await sql<{ broker: string; mode: string }>`
        select broker, mode from connectors
        where tenant_id = ${tenantId}
          and status in (${"connected"}, ${"error"})
      `;
  let synced = 0;
  for (const r of rows) {
    if (r.mode === SIMULATED_CONNECTOR_MODE) continue; // no live API to call
    try {
      await pullAndIngestBroker({
        tenantId,
        broker: r.broker as BrokerId,
      });
      synced += 1;
    } catch {
      /* last_error set in pullAndIngestBroker */
    }
  }
  return { synced };
}
