/**
 * Shared test harness for domain / API / MCP suites.
 * One PGLite DB + Vite SSR load of shipped modules (DRY).
 */
import { createHash, randomBytes } from "node:crypto";
import { createViteTestServer } from "../../scripts/vite-test-server.mjs";

let vite;
let ready;

export async function getVite() {
  if (!vite) {
    vite = await createViteTestServer();
  }
  return vite;
}

export async function load(path) {
  const v = await getVite();
  return v.ssrLoadModule(path);
}

export async function ensureReady() {
  if (ready) return ready;
  const { ensureDbReady } = await load("/src/lib/db.ts");
  await ensureDbReady();
  ready = true;
  return ready;
}

export async function closeHarness() {
  if (vite) {
    await vite.close().catch(() => {});
    vite = undefined;
    ready = false;
  }
}

/**
 * Provision a personal tenant + API key (real tenant_api_keys path).
 * @returns {{ tenant, userId, rawKey, scopes }}
 */
export async function createTenantWithApiKey(userId, scopes = "write") {
  await ensureReady();
  const { ensurePersonalTenant } = await load(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const { getSql } = await load("/src/lib/db.ts");
  const { newId } = await load("/src/lib/security/ids.ts");
  const tenant = await ensurePersonalTenant(userId);
  const rawKey = `pa_${randomBytes(24).toString("base64url")}`;
  const keyHash = createHash("sha256").update(rawKey).digest("hex");
  const keyPrefix = rawKey.slice(0, 10);
  const sql = await getSql();
  await sql`
    insert into tenant_api_keys (
      id, tenant_id, user_id, name, key_prefix, key_hash, scopes
    ) values (
      ${newId("key")}, ${tenant.id}, ${userId}, ${"test"},
      ${keyPrefix}, ${keyHash}, ${scopes}
    )
  `;
  return { tenant, userId, rawKey, scopes };
}

export function authRequest(url, rawKey, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("authorization", `Bearer ${rawKey}`);
  if (init.body && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  return new Request(url, { ...init, headers });
}

export function assert(cond, msg) {
  if (!cond) throw new Error(msg || "assertion failed");
}

export function assertStatus(res, expected, label = "status") {
  assert(
    res.status === expected,
    `${label}: expected ${expected}, got ${res.status}`,
  );
}

/** Fail if payload looks like it contains secrets. */
export function assertNoSecrets(obj, label = "payload") {
  const text = JSON.stringify(obj);
  assert(!/access_token|refresh_token|client_secret|npg_/i.test(text), `${label} leaked secrets`);
  assert(!/"ciphertext"\s*:\s*"[A-Za-z0-9+/=]{20,}"/.test(text), `${label} leaked ciphertext`);
}
