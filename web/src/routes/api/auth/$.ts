import { createFileRoute } from "@tanstack/react-router";
import { auth } from "@/lib/auth/server";

/**
 * Better Auth catch-all. Wraps handler so published (Vercel) crashes return
 * JSON instead of empty HTTP 500 — makes login failures diagnosable.
 */
async function handleAuth(request: Request): Promise<Response> {
  try {
    return await auth.handler(request);
  } catch (err) {
    const message =
      err instanceof Error
        ? err.message
        : typeof err === "string"
          ? err
          : "Auth handler failed";
    // Never leak secrets; message is enough for host/origin/DB class failures.
    const safe = message
      .replace(/postgres(ql)?:\/\/[^\s"']+/gi, "postgres://***")
      .replace(/Bearer\s+\S+/gi, "Bearer ***");
    console.error("[auth] handler error:", safe);
    return new Response(
      JSON.stringify({
        code: "AUTH_HANDLER_ERROR",
        message: safe,
      }),
      {
        status: 500,
        headers: {
          "content-type": "application/json; charset=utf-8",
          "cache-control": "no-store",
        },
      },
    );
  }
}

export const Route = createFileRoute("/api/auth/$")({
  server: {
    handlers: {
      GET: ({ request }) => handleAuth(request),
      POST: ({ request }) => handleAuth(request),
    },
  },
});
