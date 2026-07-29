import { createFileRoute } from "@tanstack/react-router";
import { jsonError } from "@/lib/portfolio/api-auth.server";
import { redactObject } from "@/lib/security/redact";

/**
 * Cron / operator endpoint for tenant-scoped OAuth token refresh.
 *
 * Auth (either):
 * - Authorization: Bearer <CRON_SECRET>  (scheduled job)
 * - Session with admin role on personal workspace (manual)
 *
 * Never returns tokens. Body options: { force?: boolean, tenantId?: string }
 * tenantId is only honored for CRON_SECRET (ops); session always uses caller's tenant.
 */

/** Shipped GET — job metadata (no side effects). */
export async function tokenRefreshGet(): Promise<Response> {
  return Response.json({
    ok: true,
    job: "token_refresh",
    auth: ["cron_secret", "session"],
    note: "POST to run. Tenant-scoped OAuth access token refresh. Never returns tokens.",
  });
}

/** Shipped POST handler for /api/v1/jobs/token-refresh */
export async function tokenRefreshPost({
  request,
}: {
  request: Request;
}): Promise<Response> {
  try {
    const { authorizeJob } = await import(
      "@/lib/portfolio/jobs-auth.server"
    );
    const principal = await authorizeJob(request);

    let body: { force?: boolean; tenantId?: string } = {};
    try {
      body = (await request.json()) as typeof body;
    } catch {
      body = {};
    }

    const { runTokenRefreshJob } = await import(
      "@/lib/portfolio/oauth/refresh.server"
    );

    const tenantId =
      principal.auth === "cron" ? body.tenantId : principal.tenantId;

    const result = await runTokenRefreshJob({
      tenantId,
      force: Boolean(body.force),
    });

    return Response.json(
      redactObject({
        ok: result.ok,
        job: {
          id: result.jobId,
          examined: result.examined,
          refreshed: result.refreshed,
          skipped: result.skipped,
          errors: result.errors,
          needsReauth: result.needsReauth,
          startedAt: result.startedAt,
          finishedAt: result.finishedAt,
        },
        results:
          principal.auth === "session" || body.tenantId
            ? result.results
            : undefined,
      }),
      { headers: { "cache-control": "no-store" } },
    );
  } catch (err) {
    return jsonError(err, 401);
  }
}

export const Route = createFileRoute("/api/v1/jobs/token-refresh")({
  server: {
    handlers: {
      POST: tokenRefreshPost,
      GET: tokenRefreshGet,
    },
  },
});
