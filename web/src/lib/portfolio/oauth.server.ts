import { getSql } from "@/lib/db";
import { newId } from "@/lib/security/ids";
import type { BrokerId } from "./brokers/catalog";
import { BROKERS } from "./brokers/catalog";
import {
  buildSchwabAuthorizeUrl,
  exchangeSchwabCode,
  schwabOAuthConfigured,
} from "./oauth/schwab.server";
import {
  buildMcpAuthorizeUrl,
  exchangeMcpCode,
  mcpOAuthConfigured,
  discoveryForBroker,
} from "./oauth/mcp-oauth.server";
import { sealConnectorSecret } from "./oauth/secrets.server";

export type OAuthStateRow = {
  id: string;
  tenantId: string;
  userId: string;
  broker: BrokerId;
  codeVerifier: string;
  redirectUri: string;
  authKind: string;
  resource: string | null;
  clientId: string | null;
  tokenEndpoint: string | null;
  authorizationEndpoint: string | null;
  scope: string | null;
};

export async function peekOAuthState(args: {
  stateId: string;
  broker: BrokerId;
}): Promise<OAuthStateRow | null> {
  const sql = await getSql();
  const rows = await sql<{
    id: string;
    tenant_id: string;
    user_id: string;
    broker: string;
    code_verifier: string;
    redirect_uri: string;
    auth_kind: string;
    resource: string | null;
    client_id: string | null;
    token_endpoint: string | null;
    authorization_endpoint: string | null;
    scope: string | null;
    expires_at: string;
  }>`
    select *
    from broker_oauth_states
    where id = ${args.stateId}
      and broker = ${args.broker}
      and expires_at > now()
    limit 1
  `;
  const r = rows[0];
  if (!r) return null;
  return {
    id: r.id,
    tenantId: r.tenant_id,
    userId: r.user_id,
    broker: r.broker as BrokerId,
    codeVerifier: r.code_verifier,
    redirectUri: r.redirect_uri,
    authKind: r.auth_kind,
    resource: r.resource,
    clientId: r.client_id,
    tokenEndpoint: r.token_endpoint,
    authorizationEndpoint: r.authorization_endpoint,
    scope: r.scope,
  };
}

export async function consumeOAuthState(args: {
  stateId: string;
  broker: BrokerId;
}): Promise<OAuthStateRow | null> {
  const peeked = await peekOAuthState(args);
  if (!peeked) return null;
  const sql = await getSql();
  await sql`
    delete from broker_oauth_states
    where id = ${args.stateId} and broker = ${args.broker}
  `;
  return peeked;
}

async function ensurePendingConnector(args: {
  tenantId: string;
  broker: BrokerId;
  mode: string;
  authKind: string;
  resourceUrl?: string | null;
}): Promise<void> {
  const sql = await getSql();
  const connId = newId("conn");
  await sql`
    insert into connectors (
      id, tenant_id, broker, mode, status, auth_kind, resource_url, mcp_url
    ) values (
      ${connId}, ${args.tenantId}, ${args.broker}, ${args.mode},
      ${"pending_oauth"}, ${args.authKind},
      ${args.resourceUrl ?? null}, ${args.resourceUrl ?? null}
    )
    on conflict (tenant_id, broker) do update set
      status = ${"pending_oauth"},
      mode = ${args.mode},
      auth_kind = ${args.authKind},
      resource_url = coalesce(${args.resourceUrl ?? null}, connectors.resource_url),
      mcp_url = coalesce(${args.resourceUrl ?? null}, connectors.mcp_url),
      updated_at = now()
  `;
}

export async function startBrokerOAuth(args: {
  tenantId: string;
  userId: string;
  broker: BrokerId;
  origin: string;
}): Promise<
  | { kind: "oauth_redirect"; authorizeUrl: string }
  | { kind: "not_configured"; message: string }
> {
  const def = BROKERS[args.broker];
  const redirectUri = `${args.origin.replace(/\/$/, "")}/api/v1/oauth/${args.broker}/callback`;

  if (args.broker === "schwab") {
    if (!(await schwabOAuthConfigured())) {
      return {
        kind: "not_configured",
        message:
          "Add your Schwab developer Client ID and secret on the setup page first.",
      };
    }
    const stateId = newId("oauth");
    const built = await buildSchwabAuthorizeUrl({
      redirectUri,
      stateId,
    });
    const sql = await getSql();
    const expires = new Date(Date.now() + 10 * 60_000).toISOString();
    await sql`
      insert into broker_oauth_states (
        id, tenant_id, user_id, broker, code_verifier, redirect_uri,
        expires_at, auth_kind
      ) values (
        ${stateId}, ${args.tenantId}, ${args.userId}, ${args.broker},
        ${built.codeVerifier}, ${redirectUri}, ${expires}::timestamptz,
        ${"direct_oauth"}
      )
    `;
    await ensurePendingConnector({
      tenantId: args.tenantId,
      broker: args.broker,
      mode: "direct_oauth",
      authKind: "direct_oauth",
    });
    return { kind: "oauth_redirect", authorizeUrl: built.authorizeUrl };
  }

  // Robinhood (and future MCP brokers)
  if (def.authKind === "remote_mcp" && discoveryForBroker(args.broker)) {
    if (!(await mcpOAuthConfigured(args.broker))) {
      return {
        kind: "not_configured",
        message: `${def.label} MCP OAuth is not available yet.`,
      };
    }
    try {
      const stateId = newId("oauth");
      const built = await buildMcpAuthorizeUrl({
        broker: args.broker,
        redirectUri,
        stateId,
      });
      const sql = await getSql();
      const expires = new Date(Date.now() + 10 * 60_000).toISOString();
      await sql`
        insert into broker_oauth_states (
          id, tenant_id, user_id, broker, code_verifier, redirect_uri,
          expires_at, auth_kind, resource, client_id, token_endpoint,
          authorization_endpoint, scope
        ) values (
          ${stateId}, ${args.tenantId}, ${args.userId}, ${args.broker},
          ${built.codeVerifier}, ${redirectUri}, ${expires}::timestamptz,
          ${"remote_mcp"}, ${built.discovery.resource}, ${built.clientId},
          ${built.discovery.tokenEndpoint}, ${built.discovery.authorizationEndpoint},
          ${built.scope}
        )
      `;
      await ensurePendingConnector({
        tenantId: args.tenantId,
        broker: args.broker,
        mode: "remote_mcp",
        authKind: "remote_mcp",
        resourceUrl: built.discovery.resource,
      });
      return { kind: "oauth_redirect", authorizeUrl: built.authorizeUrl };
    } catch (err) {
      return {
        kind: "not_configured",
        message:
          err instanceof Error
            ? err.message
            : `Could not start ${def.label} connection.`,
      };
    }
  }

  if (def.authKind === "exports_only") {
    return {
      kind: "not_configured",
      message: `${def.label} currently supports statement export only.`,
    };
  }

  return {
    kind: "not_configured",
    message: `${def.label} connection is not configured for this deployment yet.`,
  };
}

export async function exchangeOAuthCode(args: {
  broker: BrokerId;
  code: string;
  state: OAuthStateRow;
}): Promise<Record<string, unknown>> {
  if (args.broker === "schwab") {
    return exchangeSchwabCode({
      code: args.code,
      redirectUri: args.state.redirectUri,
      codeVerifier: args.state.codeVerifier,
    });
  }
  if (
    args.state.authKind === "remote_mcp" ||
    discoveryForBroker(args.broker)
  ) {
    if (
      !args.state.clientId ||
      !args.state.tokenEndpoint ||
      !args.state.codeVerifier
    ) {
      throw new Error(`Incomplete OAuth state for ${args.broker}`);
    }
    return exchangeMcpCode({
      broker: args.broker,
      code: args.code,
      redirectUri: args.state.redirectUri,
      codeVerifier: args.state.codeVerifier,
      clientId: args.state.clientId,
      tokenEndpoint: args.state.tokenEndpoint,
      resource: args.state.resource,
      scope: args.state.scope,
    });
  }
  throw new Error(`Token exchange not implemented for ${args.broker}`);
}

export { sealConnectorSecret };
