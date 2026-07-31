import { createFileRoute } from "@tanstack/react-router";

/**
 * Secret-free auth health for published debugging.
 * GET /api/v1/health/auth
 */

/** Shipped GET handler for /api/v1/health/auth */
export async function healthAuthGet({
  request,
}: {
  request: Request;
}): Promise<Response> {
  const { getAuthRuntimeStatus } = await import(
    "@/lib/auth/auth-runtime-status"
  );
  const host =
    request.headers.get("x-forwarded-host") ||
    request.headers.get("host") ||
    null;
  const status = getAuthRuntimeStatus(host);
  const note = status.publishLikelyBroken
    ? status.hostKind === "published" && status.mode === "deployed_client"
      ? "Auth client OK; missing DATABASE_URL on this *.grok.me publish. Platform must inject durable Postgres — not fixable from app code or public git."
      : "Published host misconfigured. Need durable DATABASE_URL (+ auth credentials). Grok.me: platform must inject Postgres."
    : status.hint;
  return Response.json(
    {
      ok: !status.publishLikelyBroken,
      ...status,
      trustedProxyHeaders: true,
      note,
    },
    {
      headers: { "cache-control": "no-store" },
    },
  );
}

export const Route = createFileRoute("/api/v1/health/auth")({
  server: {
    handlers: {
      GET: healthAuthGet,
    },
  },
});
