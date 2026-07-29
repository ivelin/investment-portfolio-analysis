/**
 * Resolve the Postgres connection string from process env.
 *
 * Primary: `DATABASE_URL` (Grok / Neon skill contract).
 * Fallbacks: names some hosts inject for Postgres/Neon marketplace links.
 * Last resort (sandbox publish only): optional gitignored
 * `db-bootstrap.secret.ts` when the platform fails to inject Neon.
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
 * Optional sandbox-only Neon URL (gitignored). Present when the agent
 * provisions Neon on the user's Vercel team because Grok publish did not
 * inject DATABASE_URL. Missing in CI / pure git clones — that's fine.
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

export function resolveDatabaseUrl(): string | undefined {
  if (typeof process === "undefined") return undefined;
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
  const out = { bootstrap: Boolean(bootstrapDatabaseUrl()) } as Record<
    DbUrlKey,
    boolean
  > & { bootstrap: boolean };
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
