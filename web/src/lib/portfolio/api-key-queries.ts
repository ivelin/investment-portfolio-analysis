import { createHash, randomBytes } from "node:crypto";
import { createServerFn } from "@tanstack/react-start";
import { authMiddleware } from "@/lib/auth/middleware";
import { getSql } from "@/lib/db";
import { newId } from "@/lib/security/ids";

export type ApiKeyPublic = {
  id: string;
  name: string;
  keyPrefix: string;
  scopes: string;
  createdAt: string;
  lastUsedAt: string | null;
  revokedAt: string | null;
};

export const listApiKeysFn = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async ({ context }): Promise<ApiKeyPublic[]> => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const tenant = await ensurePersonalTenant(context.userId);
    const sql = await getSql();
    const rows = await sql<{
      id: string;
      name: string;
      key_prefix: string;
      scopes: string;
      created_at: string;
      last_used_at: string | null;
      revoked_at: string | null;
    }>`
      select id, name, key_prefix, scopes,
        created_at::text as created_at,
        last_used_at::text as last_used_at,
        revoked_at::text as revoked_at
      from tenant_api_keys
      where tenant_id = ${tenant.id} and user_id = ${context.userId}
      order by created_at desc
    `;
    return rows.map((r) => ({
      id: r.id,
      name: r.name,
      keyPrefix: r.key_prefix,
      scopes: r.scopes,
      createdAt: r.created_at,
      lastUsedAt: r.last_used_at,
      revokedAt: r.revoked_at,
    }));
  });

export const createApiKeyFn = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((data: { name: string; scopes?: "read" | "write" }) => data)
  .handler(async ({ context, data }) => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const tenant = await ensurePersonalTenant(context.userId);
    const raw = `pa_${randomBytes(24).toString("base64url")}`;
    const keyHash = createHash("sha256").update(raw).digest("hex");
    const id = newId("key");
    const prefix = raw.slice(0, 10);
    const scopes = data.scopes === "write" ? "write" : "read";
    const sql = await getSql();
    await sql`
      insert into tenant_api_keys (
        id, tenant_id, user_id, name, key_prefix, key_hash, scopes
      ) values (
        ${id}, ${tenant.id}, ${context.userId}, ${data.name.slice(0, 80)},
        ${prefix}, ${keyHash}, ${scopes}
      )
    `;
    return { id, name: data.name, keyPrefix: prefix, scopes, rawKey: raw, rawOnce: raw };
  });

export const revokeApiKeyFn = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((data: { id?: string; keyId?: string }) => data)
  .handler(async ({ context, data }) => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const tenant = await ensurePersonalTenant(context.userId);
    const sql = await getSql();
    await sql`
      update tenant_api_keys set revoked_at = now()
      where id = ${data.keyId ?? data.id}
        and tenant_id = ${tenant.id}
        and user_id = ${context.userId}
        and revoked_at is null
    `;
    return { ok: true };
  });
