import { createHash } from "node:crypto";
import { getSql } from "@/lib/db";
import { getSessionUser } from "@/lib/auth/verify.server";
import { ensurePersonalTenant } from "./tenant.server";

export type ApiPrincipal = {
  auth: "session" | "api_key";
  userId: string;
  tenantId: string;
  scopes: "read" | "write";
};

export async function requireApiPrincipal(
  request: Request,
): Promise<ApiPrincipal> {
  const auth = request.headers.get("authorization") || "";
  if (auth.toLowerCase().startsWith("bearer ")) {
    const raw = auth.slice(7).trim();
    if (raw.startsWith("pa_")) {
      const hash = createHash("sha256").update(raw).digest("hex");
      const sql = await getSql();
      const rows = await sql<{
        tenant_id: string;
        user_id: string;
        scopes: string;
        id: string;
      }>`
        select tenant_id, user_id, scopes, id
        from tenant_api_keys
        where key_hash = ${hash}
          and revoked_at is null
        limit 1
      `;
      const row = rows[0];
      if (!row) {
        const err = new Error("Unauthorized");
        (err as Error & { status?: number }).status = 401;
        throw err;
      }
      await sql`
        update tenant_api_keys set last_used_at = now() where id = ${row.id}
      `;
      return {
        auth: "api_key",
        userId: row.user_id,
        tenantId: row.tenant_id,
        scopes: row.scopes === "write" ? "write" : "read",
      };
    }
  }

  const user = await getSessionUser();
  if (!user) {
    const err = new Error("Unauthorized");
    (err as Error & { status?: number }).status = 401;
    throw err;
  }
  const tenant = await ensurePersonalTenant(user.id);
  return {
    auth: "session",
    userId: user.id,
    tenantId: tenant.id,
    scopes: "write",
  };
}

export function jsonError(err: unknown, fallbackStatus = 500): Response {
  const message =
    err instanceof Error ? err.message : typeof err === "string" ? err : "Error";
  const status =
    (err as { status?: number } | null)?.status &&
    Number.isFinite((err as { status?: number }).status)
      ? Number((err as { status: number }).status)
      : message === "Unauthorized"
        ? 401
        : message === "Forbidden"
          ? 403
          : fallbackStatus;
  return Response.json(
    { ok: false, error: message === "Unauthorized" ? "Unauthorized" : message },
    { status, headers: { "cache-control": "no-store" } },
  );
}
