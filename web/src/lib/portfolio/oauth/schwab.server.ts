import { createHash, randomBytes } from "node:crypto";
import { getSql } from "@/lib/db";
import { brokerFetch } from "@/lib/portfolio/brokers/broker-http";
import { assertBrokerConnectorsReadOnly } from "@/lib/portfolio/brokers/read-only-policy";
import { sealConnectorSecret, openConnectorSecret } from "./secrets.server";

const SCHWAB_AUTH = "https://api.schwabapi.com/v1/oauth/authorize";
const SCHWAB_TOKEN = "https://api.schwabapi.com/v1/oauth/token";
const SCHWAB_TRADER = "https://api.schwabapi.com/trader/v1";

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
  assertBrokerConnectorsReadOnly();
  const creds = await resolveSchwabAppCredentials();
  if (!creds) throw new Error("Schwab app credentials not configured");

  const codeVerifier = b64url(randomBytes(32));
  const challenge = b64url(createHash("sha256").update(codeVerifier).digest());
  // Scope "api" is required by Schwab Trader API apps. Access is still limited
  // in *this product* to read-only portfolio calls (see brokerFetch policy).
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
  assertBrokerConnectorsReadOnly();
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

  const res = await brokerFetch(SCHWAB_TOKEN, {
    purpose: "oauth_token",
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      accept: "application/json",
      authorization: `Basic ${Buffer.from(`${creds.clientId}:${creds.clientSecret}`).toString("base64")}`,
    },
    body,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(
      `Schwab token exchange failed (${res.status}): ${text.slice(0, 180)}`,
    );
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
  assertBrokerConnectorsReadOnly();
  const creds = await resolveSchwabAppCredentials();
  const clientId = args.clientId || creds?.clientId;
  const clientSecret = creds?.clientSecret;
  if (!clientId || !clientSecret) {
    throw new Error("Schwab app credentials not configured");
  }
  const body = new URLSearchParams({
    grant_type: "refresh_token",
    refresh_token: args.refreshToken,
  });
  const res = await brokerFetch(SCHWAB_TOKEN, {
    purpose: "oauth_token",
    method: "POST",
    headers: {
      "content-type": "application/x-www-form-urlencoded",
      accept: "application/json",
      authorization: `Basic ${Buffer.from(`${clientId}:${clientSecret}`).toString("base64")}`,
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

/**
 * Read-only: accounts + positions for analysis.
 * Never hits /orders or any write path (enforced by brokerFetch).
 */
export async function fetchSchwabPortfolio(accessToken: string): Promise<{
  accounts: Array<{
    accountNumber: string;
    hashValue: string;
    type?: string;
    liquidationValue?: number;
    cash?: number;
  }>;
  positions: Array<{
    accountHash: string;
    symbol: string;
    quantity: number;
    marketValue: number;
    price: number;
    assetType: string;
  }>;
}> {
  assertBrokerConnectorsReadOnly();
  const headers = {
    authorization: `Bearer ${accessToken}`,
    accept: "application/json",
  };

  const numRes = await brokerFetch(
    `${SCHWAB_TRADER}/accounts/accountNumbers`,
    {
      purpose: "portfolio_read",
      method: "GET",
      headers,
    },
  );
  if (!numRes.ok) {
    throw new Error(`Schwab accountNumbers failed (${numRes.status})`);
  }
  const numbers = (await numRes.json()) as Array<{
    accountNumber?: string;
    hashValue?: string;
  }>;

  const accounts: Array<{
    accountNumber: string;
    hashValue: string;
    type?: string;
    liquidationValue?: number;
    cash?: number;
  }> = [];
  const positions: Array<{
    accountHash: string;
    symbol: string;
    quantity: number;
    marketValue: number;
    price: number;
    assetType: string;
  }> = [];

  for (const n of numbers) {
    if (!n.hashValue) continue;
    const acctRes = await brokerFetch(
      `${SCHWAB_TRADER}/accounts/${encodeURIComponent(n.hashValue)}?fields=positions`,
      {
        purpose: "portfolio_read",
        method: "GET",
        headers,
      },
    );
    if (!acctRes.ok) continue;
    const payload = (await acctRes.json()) as {
      securitiesAccount?: {
        accountNumber?: string;
        type?: string;
        currentBalances?: {
          liquidationValue?: number;
          cashBalance?: number;
          availableFunds?: number;
        };
        positions?: Array<{
          instrument?: {
            symbol?: string;
            assetType?: string;
          };
          longQuantity?: number;
          shortQuantity?: number;
          marketValue?: number;
          averagePrice?: number;
        }>;
      };
    };
    const sa = payload.securitiesAccount;
    const bal = sa?.currentBalances;
    accounts.push({
      accountNumber: n.accountNumber || sa?.accountNumber || n.hashValue,
      hashValue: n.hashValue,
      type: sa?.type,
      liquidationValue: bal?.liquidationValue,
      cash: bal?.cashBalance ?? bal?.availableFunds,
    });
    for (const p of sa?.positions ?? []) {
      const qty =
        Number(p.longQuantity || 0) - Number(p.shortQuantity || 0);
      const symbol = p.instrument?.symbol;
      if (!symbol) continue;
      positions.push({
        accountHash: n.hashValue,
        symbol,
        quantity: qty,
        marketValue: Number(p.marketValue || 0),
        price: Number(p.averagePrice || 0),
        assetType: (p.instrument?.assetType || "EQUITY").toLowerCase(),
      });
    }
  }

  return { accounts, positions };
}

void openConnectorSecret;
