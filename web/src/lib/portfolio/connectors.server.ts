import { getSql } from "@/lib/db";
import { BROKER_IDS, BROKERS, type BrokerId } from "./brokers/catalog";
import { startBrokerOAuth } from "./oauth.server";
import { schwabOAuthConfigured } from "./oauth/schwab.server";
import { pullAndIngestBroker } from "./brokers/sync.server";

const DESCRIPTIONS: Record<BrokerId, string> = {
  schwab: "Direct connection for balances and positions after you approve access at Schwab.",
  robinhood: "Connect via your Robinhood developer / MCP path when configured.",
  ibkr: "Connect Interactive Brokers when your MCP or export path is ready.",
  fidelity: "Upload or drop statement exports when live API is not available.",
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
};

async function brokerConfigured(broker: BrokerId): Promise<boolean> {
  if (broker === "schwab") return schwabOAuthConfigured();
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
    if (id === "synthetic") continue; // sample is not a connectable card
    const def = BROKERS[id];
    const row = byBroker.get(id);
    const oauthConfigured = await brokerConfigured(id);
    out.push({
      broker: id,
      label: def.label,
      description: DESCRIPTIONS[id],
      status: row?.status ?? "disconnected",
      mode: row?.mode ?? "exports_only",
      oauthConfigured,
      lastSyncAt: row?.last_sync_at ?? null,
      lastError: row?.last_error ?? null,
      authKind: row?.auth_kind ?? def.authKind,
      accountCount: acctBy.get(id) ?? 0,
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
    ? await sql<{ broker: string }>`
        select broker from connectors
        where tenant_id = ${tenantId} and status = ${"connected"} and broker = ${broker}
      `
    : await sql<{ broker: string }>`
        select broker from connectors
        where tenant_id = ${tenantId} and status = ${"connected"}
      `;
  let synced = 0;
  for (const r of rows) {
    try {
      await pullAndIngestBroker({
        tenantId,
        broker: r.broker as BrokerId,
      });
      synced += 1;
    } catch {
      /* leave last_error for later */
    }
  }
  return { synced };
}
