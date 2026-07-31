import { databaseEnvPresence, hasDatabaseUrl } from "../db-url";
import { pgliteUsableInThisRuntime } from "../runtime-env";
import { expectedBrokerRedirectUris } from "./oauth-redirect";
import {
  hasDirectSocialEnv,
  hasExplicitGrokClient,
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
  /**
   * Exact redirect_uris the Grok auth broker client must allow for this host.
   * Broker uses exact string match — missing entries → "Invalid redirect URI".
   */
  expectedBrokerRedirectUris: string[];
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
  if (process.env.GROK_AUTH_CLIENT_ID && process.env.GROK_AUTH_CLIENT_SECRET) {
    return "deployed_client";
  }
  return "preview_client";
}

function databaseMode(): DatabaseMode {
  return hasDatabaseUrl() ? "neon" : "pglite";
}

function resolvePublicOrigin(host: string | null, hostKind: HostKind): string | null {
  const fromEnv =
    process.env.BETTER_AUTH_URL?.trim() ||
    process.env.APP_PUBLIC_URL?.trim() ||
    (process.env.VERCEL_URL?.trim()
      ? `https://${process.env.VERCEL_URL.trim()}`
      : null);
  if (fromEnv) {
    try {
      return new URL(fromEnv).origin;
    } catch {
      /* fall through */
    }
  }
  if (!host) return null;
  const proto =
    hostKind === "local" || host.startsWith("127.") || host.startsWith("localhost")
      ? "http"
      : "https";
  try {
    return new URL(`${proto}://${host}`).origin;
  } catch {
    return null;
  }
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

  const origin = resolvePublicOrigin(host, hostKind);
  const expectedRedirects = origin ? expectedBrokerRedirectUris(origin) : [];

  const issues: string[] = [];
  if (enforcePublishedEnv) {
    if (mode === "unconfigured" || mode === "preview_client") {
      issues.push(
        "Sign-in needs platform Grok auth (GROK_AUTH_CLIENT_ID/SECRET on *.grok.me) " +
          "or direct GOOGLE_*/TWITTER_* credentials.",
      );
    }
    if (database === "pglite") {
      issues.push(
        "No database URL on this deploy. Sign-in needs durable Postgres (DATABASE_URL); " +
          "the sandbox in-memory DB does not work on published serverless hosts.",
      );
    }
    if (!hasStableSecret) {
      issues.push("Missing BETTER_AUTH_SECRET on published host.");
    }
  }

  const publishLikelyBroken = enforcePublishedEnv && issues.length > 0;

  let hint: string;
  if (hasDirectSocialEnv()) {
    hint =
      "Direct Google/X social + Better Auth on this origin; sessions need DATABASE_URL on published hosts.";
  } else if (mode === "deployed_client" || hasExplicitGrokClient()) {
    hint =
      "Grok broker with platform client (auth.grok.me). Client must allow exact redirect_uris listed in expectedBrokerRedirectUris.";
  } else if (mode === "preview_client") {
    hint =
      "Grok broker preview client (auth.grok.me) for sandbox/CLI; absolute redirect_uri + idp required.";
  } else if (isGrokBrokerDisabled()) {
    hint =
      "Grok broker disabled (AUTH_DISABLE_GROK_BROKER). Set GOOGLE_*/TWITTER_* or re-enable broker.";
  } else {
    hint =
      "Set platform GROK_AUTH_* (*.grok.me publish) or GOOGLE_*/TWITTER_* for direct social.";
  }

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
    hint,
    expectedBrokerRedirectUris: expectedRedirects,
  };
}
