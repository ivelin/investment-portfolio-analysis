/**
 * Remote MCP OAuth 2.1 (public client + DCR + PKCE).
 * Used for Robinhood (and ready for IBKR-style hosts).
 * App-level DCR client is cached in platform_oauth_clients — not user tokens.
 */
import { createHash, randomBytes } from "node:crypto";
import { getSql } from "@/lib/db";
import { brokerFetch } from "@/lib/portfolio/brokers/broker-http";
import { assertBrokerConnectorsReadOnly } from "@/lib/portfolio/brokers/read-only-policy";
import type { BrokerId } from "../brokers/catalog";

export type McpOAuthDiscovery = {
  resource: string;
  authorizationEndpoint: string;
  tokenEndpoint: string;
  registrationEndpoint: string;
  scopes: string[];
};

export type McpAppClient = {
  clientId: string;
  clientSecret: string | null;
  redirectUri: string;
  discovery: McpOAuthDiscovery;
};

function b64url(buf: Buffer): string {
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export function pkcePair(): { codeVerifier: string; codeChallenge: string } {
  const codeVerifier = b64url(randomBytes(32));
  const codeChallenge = b64url(
    createHash("sha256").update(codeVerifier).digest(),
  );
  return { codeVerifier, codeChallenge };
}

/** Robinhood Agentic Trading MCP (live metadata 2026-07). */
export const ROBINHOOD_MCP: McpOAuthDiscovery = {
  resource: "https://agent.robinhood.com/mcp/trading",
  authorizationEndpoint: "https://robinhood.com/oauth",
  tokenEndpoint: "https://api.robinhood.com/oauth2/token/",
  registrationEndpoint: "https://agent.robinhood.com/oauth/trading/register",
  scopes: ["internal"],
};

export function discoveryForBroker(broker: BrokerId): McpOAuthDiscovery | null {
  if (broker === "robinhood") return ROBINHOOD_MCP;
  return null;
}

/**
 * Refresh protected-resource + AS metadata when possible; fall back to known constants.
 */
export async function discoverMcpOAuth(
  broker: BrokerId,
): Promise<McpOAuthDiscovery | null> {
  assertBrokerConnectorsReadOnly();
  const base = discoveryForBroker(broker);
  if (!base) return null;
  try {
    const prm = await brokerFetch(
      "https://agent.robinhood.com/.well-known/oauth-protected-resource/mcp/trading",
      { purpose: "oauth_discovery", method: "GET", timeoutMs: 8_000 },
    );
    if (prm.ok) {
      const j = (await prm.json()) as {
        resource?: string;
        scopes_supported?: string[];
      };
      if (j.resource) base.resource = j.resource;
      if (j.scopes_supported?.length) base.scopes = j.scopes_supported;
    }
  } catch {
    /* use defaults */
  }
  try {
    const as = await brokerFetch(
      "https://agent.robinhood.com/.well-known/oauth-authorization-server",
      { purpose: "oauth_discovery", method: "GET", timeoutMs: 8_000 },
    );
    if (as.ok) {
      const j = (await as.json()) as {
        authorization_endpoint?: string;
        token_endpoint?: string;
        registration_endpoint?: string;
        scopes_supported?: string[];
      };
      if (j.authorization_endpoint)
        base.authorizationEndpoint = j.authorization_endpoint;
      if (j.token_endpoint) base.tokenEndpoint = j.token_endpoint;
      if (j.registration_endpoint)
        base.registrationEndpoint = j.registration_endpoint;
      if (j.scopes_supported?.length) base.scopes = j.scopes_supported;
    }
  } catch {
    /* use defaults */
  }
  return base;
}

export async function ensureMcpAppClient(args: {
  broker: BrokerId;
  redirectUri: string;
  clientName?: string;
}): Promise<McpAppClient> {
  const discovery = await discoverMcpOAuth(args.broker);
  if (!discovery) {
    throw new Error(`No MCP OAuth discovery for ${args.broker}`);
  }

  const sql = await getSql();
  const existing = await sql<{
    client_id: string;
    client_secret: string | null;
    redirect_uri: string;
    registration: unknown;
  }>`
    select client_id, client_secret, redirect_uri, registration
    from platform_oauth_clients
    where broker = ${args.broker}
    limit 1
  `;
  const row = existing[0];
  if (row && row.redirect_uri === args.redirectUri && row.client_id) {
    return {
      clientId: row.client_id,
      clientSecret: row.client_secret,
      redirectUri: row.redirect_uri,
      discovery,
    };
  }

  // Dynamic Client Registration (public client, PKCE, auth method none)
  const regBody = {
    client_name:
      args.clientName ||
      `Investment Portfolio Analysis (${args.broker})`,
    redirect_uris: [args.redirectUri],
    grant_types: ["authorization_code", "refresh_token"],
    response_types: ["code"],
    token_endpoint_auth_method: "none",
    scope: discovery.scopes.join(" "),
  };
  const res = await brokerFetch(discovery.registrationEndpoint, {
    purpose: "oauth_registration",
    method: "POST",
    headers: {
      "content-type": "application/json",
      accept: "application/json",
    },
    body: JSON.stringify(regBody),
    timeoutMs: 15_000,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `DCR failed for ${args.broker} (${res.status}): ${text.slice(0, 200)}`,
    );
  }
  const json = (await res.json()) as {
    client_id?: string;
    client_secret?: string | null;
    redirect_uris?: string[];
  };
  if (!json.client_id) {
    throw new Error(`DCR response missing client_id for ${args.broker}`);
  }
  const redirectUri = json.redirect_uris?.[0] || args.redirectUri;

  await sql`
    insert into platform_oauth_clients (
      broker, client_id, client_secret, redirect_uri, registration, updated_at
    ) values (
      ${args.broker},
      ${json.client_id},
      ${json.client_secret ?? null},
      ${redirectUri},
      ${JSON.stringify({ discovery, registeredAt: new Date().toISOString() })}::jsonb,
      now()
    )
    on conflict (broker) do update set
      client_id = excluded.client_id,
      client_secret = excluded.client_secret,
      redirect_uri = excluded.redirect_uri,
      registration = excluded.registration,
      updated_at = now()
  `;

  return {
    clientId: json.client_id,
    clientSecret: json.client_secret ?? null,
    redirectUri,
    discovery,
  };
}

export async function mcpOAuthConfigured(broker: BrokerId): Promise<boolean> {
  // Robinhood needs no static secrets — DCR runs at connect time.
  return Boolean(discoveryForBroker(broker));
}

export async function buildMcpAuthorizeUrl(args: {
  broker: BrokerId;
  redirectUri: string;
  stateId: string;
}): Promise<{
  authorizeUrl: string;
  codeVerifier: string;
  clientId: string;
  discovery: McpOAuthDiscovery;
  scope: string;
}> {
  const client = await ensureMcpAppClient({
    broker: args.broker,
    redirectUri: args.redirectUri,
  });
  const { codeVerifier, codeChallenge } = pkcePair();
  const scope = client.discovery.scopes.join(" ");
  const params = new URLSearchParams({
    response_type: "code",
    client_id: client.clientId,
    redirect_uri: args.redirectUri,
    scope,
    state: args.stateId,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
    // RFC 8707 resource indicator for MCP
    resource: client.discovery.resource,
  });
  return {
    authorizeUrl: `${client.discovery.authorizationEndpoint}?${params.toString()}`,
    codeVerifier,
    clientId: client.clientId,
    discovery: client.discovery,
    scope,
  };
}

export async function exchangeMcpCode(args: {
  broker: BrokerId;
  code: string;
  redirectUri: string;
  codeVerifier: string;
  clientId: string;
  tokenEndpoint: string;
  resource?: string | null;
  scope?: string | null;
}): Promise<Record<string, unknown>> {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code: args.code,
    redirect_uri: args.redirectUri,
    client_id: args.clientId,
    code_verifier: args.codeVerifier,
  });
  if (args.resource) body.set("resource", args.resource);
  if (args.scope) body.set("scope", args.scope);

  const res = await brokerFetch(args.tokenEndpoint, {
    purpose: "oauth_token",
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      accept: "application/json",
    },
    body,
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `${args.broker} token exchange failed (${res.status}): ${text.slice(0, 180)}`,
    );
  }
  const json = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
    token_type?: string;
    scope?: string;
  };
  if (!json.access_token) {
    throw new Error(`${args.broker} token exchange missing access_token`);
  }
  const expiresIn = Number(json.expires_in ?? 3600);
  return {
    kind: "remote_mcp",
    broker: args.broker,
    access_token: json.access_token,
    refresh_token: json.refresh_token,
    expires_at: Date.now() + expiresIn * 1000,
    client_id: args.clientId,
    token_endpoint: args.tokenEndpoint,
    resource: args.resource ?? null,
    scope: json.scope ?? args.scope ?? null,
    obtainedAt: new Date().toISOString(),
  };
}

export async function refreshMcpToken(args: {
  broker: string;
  refreshToken: string;
  clientId: string;
  tokenEndpoint: string;
  resource?: string | null;
}): Promise<Record<string, unknown>> {
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: args.refreshToken,
    client_id: args.clientId,
  });
  if (args.resource) body.set("resource", args.resource);
  const res = await brokerFetch(args.tokenEndpoint, {
    purpose: "oauth_token",
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      accept: "application/json",
    },
    body,
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) {
    throw new Error(`${args.broker} refresh failed (${res.status})`);
  }
  const json = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
  };
  return {
    kind: "remote_mcp",
    broker: args.broker,
    access_token: json.access_token,
    refresh_token: json.refresh_token || args.refreshToken,
    expires_at: Date.now() + Number(json.expires_in ?? 3600) * 1000,
    client_id: args.clientId,
    token_endpoint: args.tokenEndpoint,
    resource: args.resource ?? null,
    obtainedAt: new Date().toISOString(),
  };
}
