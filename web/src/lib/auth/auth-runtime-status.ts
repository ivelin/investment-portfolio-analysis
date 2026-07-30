import { databaseEnvPresence, hasDatabaseUrl } from "../db-url";
import { pgliteUsableInThisRuntime } from "../runtime-env";
import {
  hasDirectSocialEnv,
  isGrokBrokerDisabled,
  isVercelRuntime,
  resolveAuthBackendMode,
} from "./social-config";

export type AuthMode =
  | "direct_social"
  | "preview_client"
  | "deployed_client"
  | "disabled"
  | "unconfigured";
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
  pgliteUsable: boolean;
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
  if (h.endsWith(".vercel.app") || h.includes("vercel.app")) return "published";
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
  const backend = resolveAuthBackendMode(process.env);
  if (backend === "direct_social") return "direct_social";
  if (backend === "unconfigured") return "unconfigured";
  if (backend === "disabled") return "disabled";
  // backend === grok_broker
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
    process.env.BETTER_AUTH_URL?.trim() ||
      process.env.APP_PUBLIC_URL?.trim() ||
      process.env.VERCEL_URL?.trim(),
  );
  const hasStableSecret = Boolean(process.env.BETTER_AUTH_SECRET?.trim());
  const authEnabled = mode !== "disabled" && mode !== "unconfigured";

  const enforcePublishedEnv =
    (hostKind === "published" || isVercelRuntime()) && !pgliteUsable;

  const issues: string[] = [];
  if (enforcePublishedEnv) {
    if (isVercelRuntime() && (mode === "unconfigured" || mode === "preview_client")) {
      issues.push(
        "Social sign-in needs GOOGLE_CLIENT_ID/SECRET and/or TWITTER_CLIENT_ID/SECRET on Vercel (not auth.grok.me).",
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
    hint: hasDirectSocialEnv()
      ? "Direct Google/X social + Better Auth on this origin; sessions need DATABASE_URL (Neon) on published hosts."
      : mode === "preview_client" || mode === "deployed_client"
        ? "Grok broker (auth.grok.me) for sandbox/CLI; absolute redirect_uri required. Vercel uses GOOGLE_*/TWITTER_* instead."
        : isGrokBrokerDisabled()
          ? "Grok broker disabled (AUTH_DISABLE_GROK_BROKER). Set GOOGLE_*/TWITTER_* for direct social."
          : "Set GOOGLE_*/TWITTER_* for direct social, or use non-Vercel Grok broker path for sandbox/CLI.",
  };
}
