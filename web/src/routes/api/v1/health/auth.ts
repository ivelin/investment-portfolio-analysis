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
  return Response.json(
    {
      ok: !status.publishLikelyBroken,
      ...status,
      trustedProxyHeaders: true,
      note:
        "If publishLikelyBroken, platform must inject GROK_AUTH_* + DATABASE_URL + BETTER_AUTH_SECRET. Host allowlist includes *.grok.me with trustedProxyHeaders.",
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
