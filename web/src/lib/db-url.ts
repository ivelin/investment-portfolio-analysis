import { pgliteUsableInThisRuntime } from "./runtime-env";

/**
 * Resolve the Postgres connection string from process env.
 *
 * Primary: `DATABASE_URL` (Grok / Neon skill contract).
 * Fallbacks: names some hosts inject for Postgres/Neon marketplace links.
 * Last resort on serverless only: optional gitignored
 * `db-bootstrap.secret.ts` when the platform fails to inject Neon.
 *
 * HARD RULE: live preview / local dev / CI never use the publish Neon
 * bootstrap URL. Preview always stays on isolated PGLite so prod portfolio
 * and OAuth tokens are never mixed into test runs.
 *
 * Never log the value — only use it server-side.
 */
const DB_URL_KEYS = [
  "DATABASE_URL",
  "POSTGRES_URL",
  "POSTGRES_PRISMA_URL",
  "POSTGRES_URL_NON_POOLING",
  "NEON_DATABASE_URL",
] as const;

export type DbUrlKey = (typeof DB_URL_KEYS)[number];

/**
 * Optional publish-only Neon URL (gitignored). Used only when this process is
 * serverless (VERCEL) and the host did not inject DATABASE_URL.
 */
function bootstrapDatabaseUrl(): string | undefined {
  try {
    const mods = import.meta.glob("./db-bootstrap.secret.ts", {
      eager: true,
    }) as Record<string, { BOOTSTRAP_DATABASE_URL?: string }>;
    for (const mod of Object.values(mods)) {
      const value = mod.BOOTSTRAP_DATABASE_URL?.trim();
      if (value) return value;
    }
  } catch {
    /* no bootstrap file */
  }
  return undefined;
}

function normalizeUrl(url: string): string {
  return url.trim().replace(/\/$/, "");
}

/** True when `url` is the agent-managed publish bootstrap Neon (prod data). */
export function isPublishBootstrapUrl(url: string | undefined): boolean {
  if (!url) return false;
  const bootstrap = bootstrapDatabaseUrl();
  if (!bootstrap) return false;
  try {
    return normalizeUrl(url) === normalizeUrl(bootstrap);
  } catch {
    return false;
  }
}

export function resolveDatabaseUrl(): string | undefined {
  if (typeof process === "undefined") return undefined;

  // Preview / local / CI agent: isolated PGLite only. Refuse any env URL that
  // is the publish bootstrap, and do not fall through to bootstrap.
  if (pgliteUsableInThisRuntime()) {
    for (const key of DB_URL_KEYS) {
      const value = process.env[key]?.trim();
      if (value && isPublishBootstrapUrl(value)) {
        console.warn(
          `[db-url] Ignoring ${key}: publish Neon must not be used in preview/dev/CI. Using isolated PGLite.`,
        );
      }
    }
    return undefined;
  }

  // Serverless / published host only
  for (const key of DB_URL_KEYS) {
    const value = process.env[key]?.trim();
    if (value) return value;
  }
  return bootstrapDatabaseUrl();
}

/** Which known DB env keys are present (names only — no secret values). */
export function databaseEnvPresence(): Record<DbUrlKey, boolean> & {
  bootstrap: boolean;
} {
  const out = {
    bootstrap: Boolean(bootstrapDatabaseUrl()),
  } as Record<DbUrlKey, boolean> & { bootstrap: boolean };
  for (const key of DB_URL_KEYS) {
    out[key] = Boolean(
      typeof process !== "undefined" && process.env[key]?.trim(),
    );
  }
  return out;
}

export function hasDatabaseUrl(): boolean {
  return Boolean(resolveDatabaseUrl());
}
