/**
 * Pure auth-backend selection (no Better Auth / pg imports).
 * Used by server.ts and unit tests.
 *
 * Prefer direct Google + X (Twitter) OAuth on Vercel and any host that has
 * GOOGLE_* / TWITTER_* env. Never fall through to the Grok auth broker on
 * Vercel (*.vercel.app / VERCEL=1).
 */

export type SocialProviderId = "google" | "twitter";

export type AuthBackendMode =
  | "direct_social"
  | "grok_broker"
  | "disabled"
  | "unconfigured";

export type EnvLike = Record<string, string | undefined>;

function trim(env: EnvLike, key: string): string | undefined {
  const v = env[key]?.trim();
  return v ? v : undefined;
}

export function hasGoogleSocialEnv(env: EnvLike = process.env): boolean {
  return Boolean(trim(env, "GOOGLE_CLIENT_ID") && trim(env, "GOOGLE_CLIENT_SECRET"));
}

export function hasTwitterSocialEnv(env: EnvLike = process.env): boolean {
  return Boolean(trim(env, "TWITTER_CLIENT_ID") && trim(env, "TWITTER_CLIENT_SECRET"));
}

export function hasDirectSocialEnv(env: EnvLike = process.env): boolean {
  return hasGoogleSocialEnv(env) || hasTwitterSocialEnv(env);
}

export function isVercelRuntime(env: EnvLike = process.env): boolean {
  return Boolean(trim(env, "VERCEL") || trim(env, "VERCEL_ENV"));
}

export function hasExplicitGrokClient(env: EnvLike = process.env): boolean {
  return Boolean(
    trim(env, "GROK_AUTH_CLIENT_ID") && trim(env, "GROK_AUTH_CLIENT_SECRET"),
  );
}

/**
 * Which auth backend this process should use.
 *
 * - disabled: VITE_AUTH_ENABLED=false
 * - direct_social: GOOGLE_* and/or TWITTER_* present
 * - grok_broker: non-Vercel only (Grok sandbox / local), explicit or preview client
 * - unconfigured: Vercel (or any host) with neither direct social nor (non-Vercel) broker
 */
export function resolveAuthBackendMode(env: EnvLike = process.env): AuthBackendMode {
  if (trim(env, "VITE_AUTH_ENABLED") === "false") return "disabled";
  if (hasDirectSocialEnv(env)) return "direct_social";
  // Never use Grok broker / preview client on Vercel deploys.
  if (isVercelRuntime(env)) return "unconfigured";
  // Local / Grok sandbox: allow broker (preview client or injected GROK_AUTH_*).
  return "grok_broker";
}

export function isAuthConfigured(env: EnvLike = process.env): boolean {
  const mode = resolveAuthBackendMode(env);
  return mode === "direct_social" || mode === "grok_broker";
}

/** Better Auth socialProviders fragment from env (no secrets logged). */
export function buildSocialProvidersFromEnv(env: EnvLike = process.env): {
  google?: { clientId: string; clientSecret: string };
  twitter?: { clientId: string; clientSecret: string };
} {
  const out: {
    google?: { clientId: string; clientSecret: string };
    twitter?: { clientId: string; clientSecret: string };
  } = {};
  const gId = trim(env, "GOOGLE_CLIENT_ID");
  const gSecret = trim(env, "GOOGLE_CLIENT_SECRET");
  if (gId && gSecret) {
    out.google = { clientId: gId, clientSecret: gSecret };
  }
  const tId = trim(env, "TWITTER_CLIENT_ID");
  const tSecret = trim(env, "TWITTER_CLIENT_SECRET");
  if (tId && tSecret) {
    out.twitter = { clientId: tId, clientSecret: tSecret };
  }
  return out;
}

/** Which social providers are active under direct_social mode. */
export function enabledDirectProviderIds(
  env: EnvLike = process.env,
): SocialProviderId[] {
  const ids: SocialProviderId[] = [];
  if (hasGoogleSocialEnv(env)) ids.push("google");
  if (hasTwitterSocialEnv(env)) ids.push("twitter");
  return ids;
}

/**
 * Authorization hosts we expect for direct social (not auth.grok.me).
 * Used by tests / diagnostics.
 */
export const DIRECT_SOCIAL_AUTHORIZE_HOSTS = [
  "accounts.google.com",
  "twitter.com",
  "api.twitter.com",
  "x.com",
] as const;

export const GROK_BROKER_HOST = "auth.grok.me";
