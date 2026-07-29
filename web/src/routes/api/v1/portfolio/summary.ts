import { createFileRoute } from "@tanstack/react-router";
import {
  jsonError,
  requireApiPrincipal,
} from "@/lib/portfolio/api-auth.server";
import { redactObject } from "@/lib/security/redact";

/**
 * REST summary for the caller's workspace.
 * Session or tenant API key. Never returns connector secrets or raw account numbers.
 */
export const Route = createFileRoute("/api/v1/portfolio/summary")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        try {
          const principal = await requireApiPrincipal(request);
          const { getSql } = await import("@/lib/db");
          const service = await import("@/lib/portfolio/service.server");
          const sql = await getSql();
          const tenantRows = await sql<{
            id: string;
            name: string;
            slug: string;
            plan: string;
          }>`
            select id, name, slug, plan from tenants
            where id = ${principal.tenantId} limit 1
          `;
          const t = tenantRows[0];
          if (!t) {
            return Response.json(
              { ok: false, error: "Tenant not found" },
              { status: 404 },
            );
          }
          const workspace = await service.getWorkspaceSummary(principal.tenantId, t);
          const accounts = await service.listAccounts(principal.tenantId);

          const body = {
            ok: true,
            tenant: {
              id: t.id,
              name: t.name,
              slug: t.slug,
              plan: t.plan,
            },
            workspace,
            accounts: accounts.map((a) => ({
              id: a.id,
              broker: a.broker,
              displayName: a.displayName,
              accountMask: a.accountMask,
              fundSymbol: a.fundSymbol,
              isDemo: a.isDemo,
              latestNlv: a.latestNlv,
              latestAsOf: a.latestAsOf,
            })),
            security:
              "Responses are tenant-scoped. Raw account numbers and credentials are never returned.",
          };

          return Response.json(redactObject(body), {
            headers: { "cache-control": "no-store" },
          });
        } catch (err) {
          return jsonError(err, 401);
        }
      },
    },
  },
});
