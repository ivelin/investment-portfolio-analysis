import { createFileRoute } from "@tanstack/react-router";
import {
  jsonError,
  requireApiPrincipal,
} from "@/lib/portfolio/api-auth.server";
import {
  assertBrokerConnectorsReadOnly,
  assertMcpToolReadOnly,
  BROKER_READ_ONLY_PROMISE,
} from "@/lib/portfolio/brokers/read-only-policy";
import { redactObject, redactText } from "@/lib/security/redact";

/**
 * Multi-tenant MCP-compatible JSON tools endpoint.
 *
 * Auth: session cookie OR Authorization: Bearer pa_… (tenant API key).
 * Isolation: tools always run against the principal's tenant only.
 * Parity: same PortfolioService as the web dashboard / REST.
 *
 * HARD RULE: no broker order/trade tools. WRITE_TOOLS stays empty.
 * Tools only read analysis data already stored in our tenant DB.
 *
 * POST body: { "tool": string, "args"?: object }
 */

/** Tools that mutate app state — require write scope for API keys.
 *  Broker trade/order tools are never listed here. */
const WRITE_TOOLS = new Set<string>([]);

export const TOOL_CATALOG = [
  {
    name: "list_tools",
    description: "List tools (parity with web app capabilities)",
  },
  {
    name: "workspace_summary",
    description: "Workspace NLV / TWRR summary — tenant-scoped, no secrets",
  },
  {
    name: "list_accounts",
    description: "Broker accounts in this workspace (masks only)",
  },
  {
    name: "positions",
    description: "Latest positions for an account (default: primary)",
  },
  {
    name: "fund_series",
    description: "Daily fund TWRR series for an account",
  },
  {
    name: "list_connectors",
    description: "Broker connection status for this workspace (no tokens)",
  },
] as const;

/** Shipped tool dispatch — same path production MCP POST uses. */
export async function runTool(
  tool: string,
  tenantId: string,
  args: Record<string, unknown>,
): Promise<unknown> {
  assertBrokerConnectorsReadOnly();
  assertMcpToolReadOnly(tool);

  const { getSql } = await import("@/lib/db");
  const service = await import("@/lib/portfolio/service.server");
  const sql = await getSql();

  const tenantRows = await sql<{
    id: string;
    name: string;
    slug: string;
    plan: string;
  }>`
    select id, name, slug, plan from tenants where id = ${tenantId} limit 1
  `;
  const tenantMeta = tenantRows[0];
  if (!tenantMeta) {
    return { error: "Tenant not found" };
  }

  switch (tool) {
    case "list_tools":
      return { tools: TOOL_CATALOG };
    case "workspace_summary": {
      const summary = await service.getWorkspaceSummary(tenantId, tenantMeta);
      return {
        ...summary,
        security:
          "Tenant-scoped. No connector secrets or raw account numbers. Read-only analysis.",
        brokerAccess: "read_only_analysis",
      };
    }
    case "list_accounts":
      return { accounts: await service.listAccounts(tenantId) };
    case "positions": {
      const accountId = await service.resolveAccountId(
        tenantId,
        typeof args.accountId === "string" ? args.accountId : null,
      );
      if (!accountId) return { positions: [], accountId: null };
      return {
        accountId,
        positions: await service.getPositions(tenantId, accountId),
      };
    }
    case "fund_series": {
      const limit =
        typeof args.limit === "number"
          ? Math.min(Math.max(args.limit, 1), 365)
          : 90;
      const accountId = await service.resolveAccountId(
        tenantId,
        typeof args.accountId === "string" ? args.accountId : null,
      );
      if (!accountId) return { series: [], accountId: null };
      return {
        accountId,
        series: await service.getFundSeries(tenantId, accountId, limit),
      };
    }
    case "list_connectors":
      return {
        connectors: await service.getConnectorStatuses(tenantId),
        note: "OAuth is per-tenant. Tokens are never returned. Connectors are read-only.",
        brokerAccess: "read_only_analysis",
      };
    default:
      return {
        error: redactText(`Unknown tool: ${tool}`),
        tools: TOOL_CATALOG.map((t) => t.name),
      };
  }
}

export async function mcpGetHandler(): Promise<Response> {
  return Response.json({
    ok: true,
    name: "portfolio-analysis",
    mode: "multi-tenant",
    auth: ["session", "tenant_api_key"],
    tools: TOOL_CATALOG,
    writeTools: [...WRITE_TOOLS],
    placesOrders: false,
    brokerAccess: "read_only_analysis",
    isolation:
      "Every tool is scoped to the caller's tenant. No shared broker feeds.",
    note: `POST { tool, args }. ${BROKER_READ_ONLY_PROMISE}`,
  });
}

export async function mcpPostHandler({
  request,
}: {
  request: Request;
}): Promise<Response> {
  try {
    const principal = await requireApiPrincipal(request);
    let body: { tool?: string; args?: Record<string, unknown> } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      return Response.json(
        { ok: false, error: "Invalid JSON body" },
        { status: 400 },
      );
    }
    const tool = body.tool ?? "list_tools";
    if (WRITE_TOOLS.has(tool) && principal.scopes === "read") {
      return Response.json(
        { ok: false, error: "API key scope is read-only" },
        { status: 403 },
      );
    }
    try {
      assertMcpToolReadOnly(tool);
    } catch (err) {
      return Response.json(
        {
          ok: false,
          error:
            err instanceof Error ? err.message : "Broker write forbidden",
          code: "BROKER_WRITE_FORBIDDEN",
        },
        { status: 403 },
      );
    }
    const result = await runTool(tool, principal.tenantId, body.args ?? {});
    return Response.json(redactObject({ ok: true, tool, result }), {
      headers: { "cache-control": "no-store" },
    });
  } catch (err) {
    return jsonError(err, 401);
  }
}

export const Route = createFileRoute("/api/v1/mcp")({
  server: {
    handlers: {
      GET: mcpGetHandler,
      POST: mcpPostHandler,
    },
  },
});
