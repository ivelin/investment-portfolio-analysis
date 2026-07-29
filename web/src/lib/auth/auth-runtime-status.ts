import { databaseEnvPresence, hasDatabaseUrl } from "../db-url";
import { pgliteUsableInThisRuntime } from "../runtime-env";

export type AuthMode = "preview_client" | "deployed_client" | "disabled";
export type HostKind = "sandbox" | "published" | "local" | "unknown";
export type DatabaseMode = "neon" | "pglite";

export type AuthRuntimeStatus = {
  authEnabled: boolean;
  mode: AuthMode;
  database: DatabaseMode;
  hasBetterAuthUrl: boolean;
  hasStableSecret: boolean;
  host: string | null;
  hostKind: HostKind;
  /** True only on real serverless published hosts missing required env. */
  publishLikelyBroken: boolean;
  /**
   * True when this Node process can use the in-memory PGLite fallback
   * (long-lived sandbox / local). False on Vercel/serverless where PGLite
   * cannot persist across invocations.
   */
  pgliteUsable: boolean;
  /** Which known DB env *keys* are set (boolean only — never values). */
  databaseEnv: Record<string, boolean>;
  issues: string[];
  hint: string;
};

export { pgliteUsableInThisRuntime };

function classifyHost(host: string | null): HostKind {
  if (!host) return "unknown";
  const h = host.toLowerCase();
  if (
    h.includes("grok-sandbox.com") ||
    (h.includes("localhost") && h.includes("sandbox"))
  ) {
    return "sandbox";
  }
  if (h.endsWith(".grok-sandbox.com")) return "sandbox";
  if (h.endsWith(".grok.me") || h === "grok.me") return "published";
  if (
    h === "localhost" ||
    h.startsWith("localhost:") ||
    h.startsWith("127.0.0.1") ||
    h.startsWith("[::1]")
  ) {
    return "local";
  }
  return "unknown";
}

function authMode(): AuthMode {
  if (process.env.VITE_AUTH_ENABLED === "false") return "disabled";
  if (process.env.GROK_AUTH_CLIENT_ID && process.env.GROK_AUTH_CLIENT_SECRET) {
    return "deployed_client";
  }
  return "preview_client";
}

function databaseMode(): DatabaseMode {
  return hasDatabaseUrl() ? "neon" : "pglite";
}

/**
 * Secret-free runtime status for login UX + /api/v1/health/auth.
 */
export function getAuthRuntimeStatus(host: string | null): AuthRuntimeStatus {
  const hostKind = classifyHost(host);
  const mode = authMode();
  const database = databaseMode();
  const pgliteUsable = pgliteUsableInThisRuntime();
  const databaseEnv = databaseEnvPresence();
  const hasBetterAuthUrl = Boolean(
    process.env.BETTER_AUTH_URL?.trim() || process.env.APP_PUBLIC_URL?.trim(),
  );
  const hasStableSecret = Boolean(process.env.BETTER_AUTH_SECRET?.trim());
  const authEnabled = mode !== "disabled";

  // Only enforce published-host env when this process is actually serverless.
  // Sandbox processes that happen to see a *.grok.me Host header still run
  // PGLite + the preview OAuth client successfully.
  const enforcePublishedEnv = hostKind === "published" && !pgliteUsable;

  const issues: string[] = [];
  if (enforcePublishedEnv) {
    if (mode === "preview_client") {
      issues.push(
        "Published host is still using the preview sign-in client. Platform must inject GROK_AUTH_CLIENT_ID + GROK_AUTH_CLIENT_SECRET.",
      );
    }
    if (database === "pglite") {
      issues.push(
        "No database URL on this deploy. Sign-in needs Postgres (Neon); the sandbox in-memory DB does not work on published serverless hosts.",
      );
    }
    if (!hasStableSecret) {
      issues.push("Missing BETTER_AUTH_SECRET on published host.");
    }
    if (!hasBetterAuthUrl) {
      issues.push(
        "Missing BETTER_AUTH_URL / APP_PUBLIC_URL (public https origin) on published host.",
      );
    }
  }

  const publishLikelyBroken = enforcePublishedEnv && issues.length > 0;

  return {
    authEnabled,
    mode,
    database,
    hasBetterAuthUrl:
      hasBetterAuthUrl ||
      hostKind === "sandbox" ||
      hostKind === "local" ||
      pgliteUsable,
    hasStableSecret: hasStableSecret || !enforcePublishedEnv,
    host,
    hostKind,
    publishLikelyBroken,
    pgliteUsable,
    databaseEnv,
    issues,
    hint: pgliteUsable
      ? "Live preview / local: PGLite + preview (or injected) auth client. Published serverless needs GROK_AUTH_*, BETTER_AUTH_*, and DATABASE_URL."
      : "Published serverless sign-in needs platform env: GROK_AUTH_CLIENT_ID + SECRET, BETTER_AUTH_SECRET, BETTER_AUTH_URL (your https origin), and DATABASE_URL.",
  };
}
