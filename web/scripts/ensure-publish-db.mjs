#!/usr/bin/env node
/**
 * Grok production DB provisioning (agent-owned — never requires the user to
 * claim a Neon project into their personal Vercel/Neon account).
 *
 * Sequence (runs on `npm run prebuild` / `db:ensure`):
 *   1. Prefer platform-injected DATABASE_URL / aliases when present.
 *   2. Else refresh gitignored bootstrap from neon.new if the existing
 *      claimable DB is still healthy and not near expiry.
 *   3. Else provision a new claimable Neon DB (no account) and bake the URL
 *      into src/lib/db-bootstrap.secret.ts for the serverless bundle.
 *
 * Preview keeps PGLite (db-url only uses bootstrap on serverless).
 * Unclaimed neon.new DBs last ~72h; this script re-provisions automatically
 * on the next build — no user claim step.
 */
import { writeFileSync, readFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import pg from "pg";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const secretPath = join(root, "src/lib/db-bootstrap.secret.ts");
const metaPath = join(root, "src/lib/db-bootstrap.meta.json");

/** Re-provision when fewer than this many ms remain before expires_at. */
const RENEW_WITHIN_MS = 24 * 60 * 60 * 1000;

const ENV_KEYS = [
  "DATABASE_URL",
  "POSTGRES_URL",
  "POSTGRES_PRISMA_URL",
  "POSTGRES_URL_NON_POOLING",
  "NEON_DATABASE_URL",
];

function envDatabaseUrl() {
  for (const key of ENV_KEYS) {
    const v = process.env[key]?.trim();
    if (v) return { key, url: v };
  }
  return null;
}

function normalizePgUrl(url) {
  let u = String(url).trim();
  u = u.replace(/channel_binding=require&?/g, "").replace(/[?&]$/, "");
  if (!/[?&]sslmode=/.test(u)) {
    u += (u.includes("?") ? "&" : "?") + "sslmode=require";
  }
  if (!/[?&]uselibpqcompat=/.test(u)) {
    u += "&uselibpqcompat=true";
  }
  return u.replace("?&", "?").replace(/&&+/g, "&");
}

function readBootstrapUrl() {
  if (!existsSync(secretPath)) return null;
  const text = readFileSync(secretPath, "utf8");
  const m = text.match(
    /BOOTSTRAP_DATABASE_URL\s*=\s*\n?\s*["'`]([^"'`]+)["'`]/,
  );
  return m?.[1]?.trim() || null;
}

function readMeta() {
  if (!existsSync(metaPath)) return {};
  try {
    return JSON.parse(readFileSync(metaPath, "utf8"));
  } catch {
    return {};
  }
}

function writeBootstrap(url, meta = {}) {
  const normalized = normalizePgUrl(url);
  const body =
    `/**\n` +
    ` * Server-only bootstrap Postgres for Grok *.grok.me when the platform\n` +
    ` * does not inject DATABASE_URL. Loaded only on serverless (db-url.ts).\n` +
    ` * Gitignored — managed by scripts/ensure-publish-db.mjs (agent-owned).\n` +
    ` * Do NOT ask the product owner to claim this into a personal Neon/Vercel org.\n` +
    ` */\n` +
    `export const BOOTSTRAP_DATABASE_URL =\n  ${JSON.stringify(normalized)};\n`;
  mkdirSync(dirname(secretPath), { recursive: true });
  writeFileSync(secretPath, body, "utf8");
  const prev = readMeta();
  const safeMeta = {
    ...prev,
    ...meta,
    managedBy: "ensure-publish-db",
    userActionRequired: false,
    updatedAt: new Date().toISOString(),
  };
  delete safeMeta.connection_string;
  delete safeMeta.connectionString;
  // Keep claimUrl out of user-facing docs; agent-only lifecycle metadata.
  writeFileSync(metaPath, JSON.stringify(safeMeta, null, 2) + "\n", "utf8");
  return normalized;
}

async function canConnect(url) {
  const pool = new pg.Pool({
    connectionString: normalizePgUrl(url),
    max: 1,
    connectionTimeoutMillis: 12_000,
    ssl: { rejectUnauthorized: false },
  });
  try {
    await pool.query("select 1 as ok");
    return true;
  } catch {
    return false;
  } finally {
    await pool.end().catch(() => {});
  }
}

function isNearExpiry(expiresAt) {
  if (!expiresAt) return false;
  const t = Date.parse(expiresAt);
  if (Number.isNaN(t)) return false;
  return t - Date.now() < RENEW_WITHIN_MS;
}

async function fetchClaimable(id) {
  const res = await fetch(`https://neon.new/api/v1/database/${id}`);
  if (!res.ok) return null;
  try {
    return await res.json();
  } catch {
    return null;
  }
}

async function provisionClaimable() {
  const res = await fetch("https://neon.new/api/v1/database", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ref: "investment-portfolio-analysis-grok" }),
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error(
      `neon.new non-JSON response (${res.status}): ${text.slice(0, 200)}`,
    );
  }
  if (!res.ok || !data.connection_string) {
    throw new Error(
      `neon.new provision failed (${res.status}): ${data.message || text.slice(0, 200)}`,
    );
  }
  return data;
}

function metaFromClaimable(data, source) {
  return {
    source,
    id: data.id,
    neonProjectId: data.neon_project_id,
    expiresAt: data.expires_at,
    status: data.status,
    // Stored for agent renewal only — not a user task.
    _agentClaimUrl: data.claim_url,
    note: "Agent-managed claimable Postgres for Grok publish. Auto-renewed on build; do not claim into a personal Vercel/Neon account.",
  };
}

async function provisionAndWrite(reason) {
  console.log(`[ensure-publish-db] provisioning new claimable Neon (${reason})`);
  const data = await provisionClaimable();
  writeBootstrap(data.connection_string, metaFromClaimable(data, "neon.new"));
  if (!(await canConnect(data.connection_string))) {
    throw new Error(
      "[ensure-publish-db] provisioned DB failed connectivity check",
    );
  }
  console.log(
    `[ensure-publish-db] ready id=${data.id} expires_at=${data.expires_at}`,
  );
  console.log(
    "[ensure-publish-db] lifecycle is agent-owned; no user Neon/Vercel claim required",
  );
}

async function main() {
  const fromEnv = envDatabaseUrl();
  if (fromEnv) {
    console.log(
      `[ensure-publish-db] platform env ${fromEnv.key} present — using injected DB (no bootstrap)`,
    );
    // Clear stale "user must claim" notes if any
    if (existsSync(metaPath)) {
      const prev = readMeta();
      writeFileSync(
        metaPath,
        JSON.stringify(
          {
            ...prev,
            source: "platform-env",
            key: fromEnv.key,
            userActionRequired: false,
            managedBy: "platform",
            updatedAt: new Date().toISOString(),
          },
          null,
          2,
        ) + "\n",
      );
    }
    return;
  }

  const meta = readMeta();
  const existingUrl = readBootstrapUrl();

  // Prefer refreshing credentials from neon.new when we still know the id.
  if (meta.id) {
    process.stdout.write(
      `[ensure-publish-db] refreshing claimable id=${meta.id}… `,
    );
    const remote = await fetchClaimable(meta.id);
    if (remote?.connection_string && !isNearExpiry(remote.expires_at)) {
      if (await canConnect(remote.connection_string)) {
        console.log("ok");
        writeBootstrap(
          remote.connection_string,
          metaFromClaimable(remote, "neon.new-refresh"),
        );
        return;
      }
      console.log("unreachable");
    } else if (remote && isNearExpiry(remote.expires_at)) {
      console.log("near expiry — rotating");
    } else {
      console.log("missing/expired");
    }
  }

  if (existingUrl && !isNearExpiry(meta.expiresAt)) {
    process.stdout.write("[ensure-publish-db] probing local bootstrap… ");
    if (await canConnect(existingUrl)) {
      console.log("ok");
      writeBootstrap(existingUrl, {
        source: "reuse",
        userActionRequired: false,
      });
      return;
    }
    console.log("unreachable — rotating");
  }

  await provisionAndWrite(existingUrl ? "rotate" : "initial");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
