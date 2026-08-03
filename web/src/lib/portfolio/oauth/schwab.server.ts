import { createHash, randomBytes } from "node:crypto";
import { getSql } from "@/lib/db";
import { brokerFetch } from "@/lib/portfolio/brokers/broker-http";
import { assertBrokerConnectorsReadOnly } from "@/lib/portfolio/brokers/read-only-policy";
import {
  assembleSchwabPortfolio,
  parseSchwabAccountNumbers,
} from "@/lib/portfolio/brokers/schwab-contract";
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
    throw new Error("Schwab re-authorization required — app credentials missing");
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
    const text = await res.text().catch(() => "");
    if (res.status === 400 || res.status === 401) {
      throw new Error(
        `Schwab re-authorization required (${res.status}): ${text.slice(0, 120)}`,
      );
    }
    throw new Error(
      `Schwab refresh failed (${res.status}): ${text.slice(0, 120)}`,
    );
  }
  const json = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
    expires_in?: number;
  };
  if (!json.access_token) {
    throw new Error("Schwab re-authorization required — empty access_token");
  }
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

export type SchwabPortfolioResult = {
  accounts: Array<{
    accountNumber: string;
    hashValue: string;
    type?: string;
    nickname?: string;
    liquidationValue?: number | null;
    cash?: number | null;
    dataQuality: number;
  }>;
  positions: Array<{
    accountHash: string;
    symbol: string;
    quantity: number;
    marketValue: number | null;
    price: number | null;
    assetType: string;
    dataQuality: number;
  }>;
  warnings: string[];
  contractVersion: string;
};

/**
 * Read-only: accounts + positions for analysis.
 * Contract-validated; never hits /orders. On total failure throws so callers
 * keep last-known-good rows (no wipe).
 */
export async function fetchSchwabPortfolio(
  accessToken: string,
): Promise<SchwabPortfolioResult> {
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
  if (numRes.status === 401 || numRes.status === 403) {
    throw new Error(
      `Schwab re-authorization required (accountNumbers ${numRes.status})`,
    );
  }
  if (!numRes.ok) {
    throw new Error(`Schwab accountNumbers failed (${numRes.status})`);
  }

  let numbersRaw: unknown;
  try {
    numbersRaw = await numRes.json();
  } catch {
    throw new Error(
      "Schwab accountNumbers unparseable JSON — possible format change",
    );
  }

  const numbers = parseSchwabAccountNumbers(numbersRaw);
  if (numbers.contractMismatch) {
    throw new Error(
      `Schwab contract mismatch on accountNumbers: ${numbers.errors.join("; ") || "unexpected shape"}`,
    );
  }
  if (numbers.entries.length === 0) {
    return {
      accounts: [],
      positions: [],
      warnings: numbers.warnings,
      contractVersion: "trader.v1.accounts.2024",
    };
  }

  const accountPayloads: Array<{
    identity: { accountNumber: string; hashValue: string };
    body: unknown;
    httpOk: boolean;
  }> = [];

  for (const n of numbers.entries) {
    const acctRes = await brokerFetch(
      `${SCHWAB_TRADER}/accounts/${encodeURIComponent(n.hashValue)}?fields=positions`,
      {
        purpose: "portfolio_read",
        method: "GET",
        headers,
      },
    );
    if (acctRes.status === 401 || acctRes.status === 403) {
      throw new Error(
        `Schwab re-authorization required (account ${acctRes.status})`,
      );
    }
    let body: unknown = null;
    let httpOk = acctRes.ok;
    if (acctRes.ok) {
      try {
        body = await acctRes.json();
      } catch {
        httpOk = false;
        body = null;
      }
    }
    accountPayloads.push({ identity: n, body, httpOk });
  }

  const assembled = assembleSchwabPortfolio({
    accountNumbersRaw: numbersRaw,
    accountPayloads,
  });

  if (assembled.contractMismatch) {
    throw new Error(
      `Schwab contract mismatch: ${assembled.errors.join("; ") || "unsupported payload"}`,
    );
  }
  if (!assembled.ok && assembled.errors.length) {
    throw new Error(
      assembled.errors.join("; ") || "Schwab portfolio fetch failed",
    );
  }

  return {
    accounts: assembled.accounts.map((a) => ({
      accountNumber: a.accountNumber,
      hashValue: a.hashValue,
      type: a.type,
      nickname: a.nickname,
      liquidationValue: a.liquidationValue,
      cash: a.cash,
      dataQuality: a.dataQuality,
    })),
    positions: assembled.positions.map((p) => ({
      accountHash: p.accountHash,
      symbol: p.symbol,
      quantity: p.quantity,
      marketValue: p.marketValue,
      price: p.price,
      assetType: p.assetType,
      dataQuality: p.dataQuality,
    })),
    warnings: [...numbers.warnings, ...assembled.warnings],
    contractVersion: assembled.contractVersion,
  };
}

void openConnectorSecret;
