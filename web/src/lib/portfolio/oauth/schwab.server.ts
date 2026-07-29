import { createHash, randomBytes } from "node:crypto";
import { getSql } from "@/lib/db";
import { sealConnectorSecret, openConnectorSecret } from "./secrets.server";

const SCHWAB_AUTH =
  "https://api.schwabapi.com/v1/oauth/authorize";
const SCHWAB_TOKEN =
  "https://api.schwabapi.com/v1/oauth/token";

export type SchwabAppCredentials = {
  clientId: string;
  clientSecret: string;
  redirectUri: string;
};

function b64url(buf: Buffer): string {
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

export async function resolveSchwabAppCredentials(): Promise<SchwabAppCredentials | null> {
  const envId = process.env.SCHWAB_CLIENT_ID?.trim();
  const envSecret = process.env.SCHWAB_CLIENT_SECRET?.trim();
  const envRedirect = process.env.SCHWAB_REDIRECT_URI?.trim();
  if (envId && envSecret) {
    return {
      clientId: envId,
      clientSecret: envSecret,
      redirectUri: envRedirect || "",
    };
  }

  const sql = await getSql();
  const rows = await sql<{
    client_id: string;
    client_secret: string | null;
    redirect_uri: string;
  }>`
    select client_id, client_secret, redirect_uri
    from platform_oauth_clients
    where broker = ${"schwab"}
    limit 1
  `;
  const row = rows[0];
  if (!row?.client_id || !row.client_secret) return null;
  return {
    clientId: row.client_id,
    clientSecret: row.client_secret,
    redirectUri: row.redirect_uri,
  };
}

export async function schwabOAuthConfigured(): Promise<boolean> {
  const c = await resolveSchwabAppCredentials();
  return Boolean(c?.clientId && c.clientSecret);
}

export async function saveSchwabAppCredentials(args: {
  clientId: string;
  clientSecret: string;
  redirectUri: string;
}): Promise<void> {
  const sql = await getSql();
  // Store secret in platform table (app-level DCR/app credentials, not user tokens).
  // For defense-in-depth we also keep a sealed copy in registration meta.
  const sealed = sealConnectorSecret({
    client_secret: args.clientSecret,
  });
  await sql`
    insert into platform_oauth_clients (
      broker, client_id, client_secret, redirect_uri, registration, updated_at
    ) values (
      ${"schwab"},
      ${args.clientId},
      ${args.clientSecret},
      ${args.redirectUri},
      ${JSON.stringify({ sealedSecret: sealed })}::jsonb,
      now()
    )
    on conflict (broker) do update set
      client_id = excluded.client_id,
      client_secret = excluded.client_secret,
      redirect_uri = excluded.redirect_uri,
      registration = excluded.registration,
      updated_at = now()
  `;
}

export async function buildSchwabAuthorizeUrl(args: {
  redirectUri: string;
  stateId: string;
}): Promise<{ authorizeUrl: string; codeVerifier: string }> {
  const creds = await resolveSchwabAppCredentials();
  if (!creds) throw new Error("Schwab app credentials not configured");

  const codeVerifier = b64url(randomBytes(32));
  const challenge = b64url(createHash("sha256").update(codeVerifier).digest());
  const params = new URLSearchParams({
    client_id: creds.clientId,
    redirect_uri: args.redirectUri || creds.redirectUri,
    response_type: "code",
    scope: "api",
    state: args.stateId,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  return {
    authorizeUrl: `${SCHWAB_AUTH}?${params.toString()}`,
    codeVerifier,
  };
}

export async function exchangeSchwabCode(args: {
  code: string;
  redirectUri: string;
  codeVerifier: string;
}): Promise<Record<string, unknown>> {
  const creds = await resolveSchwabAppCredentials();
  if (!creds) throw new Error("Schwab app credentials not configured");

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code: args.code,
    redirect_uri: args.redirectUri || creds.redirectUri,
    code_verifier: args.codeVerifier,
    client_id: creds.clientId,
    client_secret: creds.clientSecret,
  });

  const res = await fetch(SCHWAB_TOKEN, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      accept: "application/json",
    },
    body,
  });
  if (!res.ok) {
    throw new Error(`Schwab token exchange failed (${res.status})`);
  }
  const json = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
    token_type?: string;
  };
  const expiresIn = Number(json.expires_in ?? 1800);
  return {
    kind: "direct_oauth",
    broker: "schwab",
    access_token: json.access_token,
    refresh_token: json.refresh_token,
    expires_at: Date.now() + expiresIn * 1000,
    client_id: creds.clientId,
    obtainedAt: new Date().toISOString(),
  };
}

export async function refreshSchwabToken(args: {
  refreshToken: string;
  clientId?: string;
}): Promise<Record<string, unknown>> {
  const creds = await resolveSchwabAppCredentials();
  const clientId = args.clientId || creds?.clientId;
  const clientSecret = creds?.clientSecret;
  if (!clientId || !clientSecret) {
    throw new Error("Schwab app credentials not configured");
  }
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: args.refreshToken,
    client_id: clientId,
    client_secret: clientSecret,
  });
  const res = await fetch(SCHWAB_TOKEN, {
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      accept: "application/json",
    },
    body,
  });
  if (!res.ok) {
    throw new Error(`Schwab refresh failed (${res.status})`);
  }
  const json = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
  };
  const expiresIn = Number(json.expires_in ?? 1800);
  return {
    kind: "direct_oauth",
    broker: "schwab",
    access_token: json.access_token,
    refresh_token: json.refresh_token || args.refreshToken,
    expires_at: Date.now() + expiresIn * 1000,
    client_id: clientId,
    obtainedAt: new Date().toISOString(),
  };
}

// silence unused import if tree-shaken tools expect open
void openConnectorSecret;
