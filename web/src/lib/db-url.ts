/**
 * Resolve the Postgres connection string from process env.
 *
 * Primary: `DATABASE_URL` (Grok / Neon skill contract).
 * Fallbacks: names some hosts inject for Postgres/Neon marketplace links.
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

export function resolveDatabaseUrl(): string | undefined {
  if (typeof process === "undefined") return undefined;
  for (const key of DB_URL_KEYS) {
    const value = process.env[key]?.trim();
    if (value) return value;
  }
  return undefined;
}

/** Which known DB env keys are present (names only — no secret values). */
export function databaseEnvPresence(): Record<DbUrlKey, boolean> {
  const out = {} as Record<DbUrlKey, boolean>;
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
