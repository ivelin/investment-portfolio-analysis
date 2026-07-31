import { getSql } from "@/lib/db";
import { newId } from "@/lib/security/ids";
import {
  classifyRefreshAction,
  DEFAULT_REFRESH_SKEW_MS,
  type RefreshAction,
} from "./refresh-decision";
import { openConnectorSecret, sealConnectorSecret } from "./secrets.server";
import { refreshSchwabToken } from "./schwab.server";
import { refreshMcpToken } from "./mcp-oauth.server";
import { brokerFetch } from "@/lib/portfolio/brokers/broker-http";

export { classifyRefreshAction, DEFAULT_REFRESH_SKEW_MS };

export type RefreshResultRow = {
  tenantId: string;
  connectorId: string;
  broker: string;
  action: RefreshAction | "error";
  message?: string;
};

export type TokenRefreshJobResult = {
  ok: boolean;
  jobId: string;
  examined: number;
  refreshed: number;
  skipped: number;
  errors: number;
  needsReauth: number;
  startedAt: string;
  finishedAt: string;
  results: RefreshResultRow[];
};

async function refreshOne(
  tokens: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const broker = String(tokens.broker || "");
  if (broker === "schwab") {
    return refreshSchwabToken({
      refreshToken: String(tokens.refresh_token),
      clientId: tokens.client_id ? String(tokens.client_id) : undefined,
    });
  }
  if (
    (broker === "robinhood" || tokens.kind === "remote_mcp") &&
    tokens.token_endpoint &&
    tokens.client_id &&
    tokens.refresh_token
  ) {
    return refreshMcpToken({
      broker,
      refreshToken: String(tokens.refresh_token),
      clientId: String(tokens.client_id),
      tokenEndpoint: String(tokens.token_endpoint),
      resource: tokens.resource ? String(tokens.resource) : null,
    });
  }
  // Generic OAuth refresh if token_endpoint present
  const tokenEndpoint = tokens.token_endpoint
    ? String(tokens.token_endpoint)
    : null;
  if (tokenEndpoint) {
    const body = new URLSearchParams({
      grant_type: "refresh_token",
      refresh_token: String(tokens.refresh_token),
    });
    if (tokens.client_id) body.set("client_id", String(tokens.client_id));
    const res = await brokerFetch(tokenEndpoint, {
      purpose: "oauth_token",
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body,
    });
    if (!res.ok) throw new Error(`refresh failed ${res.status}`);
    const json = (await res.json()) as {
      access_token?: string;
      refresh_token?: string;
      expires_in?: number;
    };
    return {
      ...tokens,
      access_token: json.access_token,
      refresh_token: json.refresh_token || tokens.refresh_token,
      expires_at: Date.now() + Number(json.expires_in ?? 1800) * 1000,
      obtainedAt: new Date().toISOString(),
    };
  }
  throw new Error(`No refresh path for broker ${broker}`);
}

/**
 * Tenant-scoped OAuth access-token renewal.
 * One connector at a time; seal only into that tenant's connector_secrets.
 */
export async function runTokenRefreshJob(
  opts: {
    tenantId?: string;
    force?: boolean;
  } = {},
): Promise<TokenRefreshJobResult> {
  const sql = await getSql();
  const startedAt = new Date().toISOString();
  const jobId = newId("job");

  await sql`
    insert into job_runs (id, tenant_id, job_name, status, started_at)
    values (
      ${jobId},
      ${opts.tenantId ?? null},
      ${"token_refresh"},
      ${"running"},
      ${startedAt}::timestamptz
    )
  `;

  const rows = opts.tenantId
    ? await sql<{
        connector_id: string;
        tenant_id: string;
        broker: string;
        ciphertext: string;
      }>`
      select s.connector_id, s.tenant_id, c.broker, s.ciphertext
      from connector_secrets s
      join connectors c on c.id = s.connector_id
      where s.tenant_id = ${opts.tenantId}
    `
    : await sql<{
        connector_id: string;
        tenant_id: string;
        broker: string;
        ciphertext: string;
      }>`
      select s.connector_id, s.tenant_id, c.broker, s.ciphertext
      from connector_secrets s
      join connectors c on c.id = s.connector_id
    `;

  const results: RefreshResultRow[] = [];
  let refreshed = 0;
  let skipped = 0;
  let errors = 0;
  let needsReauth = 0;

  for (const row of rows) {
    let tokens: Record<string, unknown> | null = null;
    try {
      tokens = openConnectorSecret(row.ciphertext);
    } catch {
      errors += 1;
      results.push({
        tenantId: row.tenant_id,
        connectorId: row.connector_id,
        broker: row.broker,
        action: "error",
        message: "unseal_failed",
      });
      continue;
    }

    const action = classifyRefreshAction(
      {
        access_token: tokens.access_token as string | undefined,
        refresh_token: tokens.refresh_token as string | undefined,
        expires_at: tokens.expires_at as number | undefined,
      },
      { force: opts.force },
    );

    if (action === "skip") {
      skipped += 1;
      results.push({
        tenantId: row.tenant_id,
        connectorId: row.connector_id,
        broker: row.broker,
        action,
      });
      continue;
    }

    if (action === "needs_reauth") {
      needsReauth += 1;
      await sql`
        update connectors set
          status = ${"error"},
          last_error = ${"Re-authorization required"},
          updated_at = now()
        where id = ${row.connector_id} and tenant_id = ${row.tenant_id}
      `;
      results.push({
        tenantId: row.tenant_id,
        connectorId: row.connector_id,
        broker: row.broker,
        action,
      });
      continue;
    }

    try {
      const next = await refreshOne({ ...tokens, broker: row.broker });
      const ciphertext = sealConnectorSecret(next);
      await sql`
        update connector_secrets set
          ciphertext = ${ciphertext},
          updated_at = now()
        where connector_id = ${row.connector_id}
          and tenant_id = ${row.tenant_id}
      `;
      await sql`
        update connectors set
          last_error = null,
          updated_at = now()
        where id = ${row.connector_id} and tenant_id = ${row.tenant_id}
      `;
      refreshed += 1;
      results.push({
        tenantId: row.tenant_id,
        connectorId: row.connector_id,
        broker: row.broker,
        action: "refresh",
      });
    } catch (err) {
      errors += 1;
      const message = err instanceof Error ? err.message : "refresh_failed";
      await sql`
        update connectors set
          last_error = ${message.slice(0, 200)},
          updated_at = now()
        where id = ${row.connector_id} and tenant_id = ${row.tenant_id}
      `;
      results.push({
        tenantId: row.tenant_id,
        connectorId: row.connector_id,
        broker: row.broker,
        action: "error",
        message: "refresh_failed",
      });
    }
  }

  const finishedAt = new Date().toISOString();
  await sql`
    update job_runs set
      status = ${errors > 0 && refreshed === 0 ? "error" : "success"},
      finished_at = ${finishedAt}::timestamptz,
      message = ${`examined=${rows.length} refreshed=${refreshed}`}
    where id = ${jobId}
  `;

  return {
    ok: errors === 0,
    jobId,
    examined: rows.length,
    refreshed,
    skipped,
    errors,
    needsReauth,
    startedAt,
    finishedAt,
    results,
  };
}
