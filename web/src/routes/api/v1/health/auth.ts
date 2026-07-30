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
    ? "Published host misconfigured. Vercel: set GOOGLE_*/TWITTER_* + DATABASE_URL + BETTER_AUTH_SECRET (see AUTH.md). Grok.me: needs platform DATABASE_URL (not fixable from public git)."
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
