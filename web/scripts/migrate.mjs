#!/usr/bin/env node
/**
 * Deploy-time database migrator (node-postgres, `pg`).
 *
 * Runs during `npm run build`. Resolves URL from:
 *   1. DATABASE_URL / Postgres aliases (platform injection)
 *   2. gitignored src/lib/db-bootstrap.secret.ts (claimable Neon publish fallback)
 *
 * No URL → skip; PGLite applies the same files at preview startup.
 */
import { createRequire } from "node:module";
import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import pg from "pg";

const require = createRequire(import.meta.url);
const fs = require("node:fs");

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function resolveDatabaseUrl() {
  for (const key of [
    "DATABASE_URL",
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "POSTGRES_URL_NON_POOLING",
    "NEON_DATABASE_URL",
  ]) {
    const value = process.env[key]?.trim();
    if (value) return { key, url: value };
  }
  const secretPath = join(root, "src/lib/db-bootstrap.secret.ts");
  if (fs.existsSync(secretPath)) {
    const text = fs.readFileSync(secretPath, "utf8");
    const m = text.match(
      /BOOTSTRAP_DATABASE_URL\s*=\s*\n?\s*["'`]([^"'`]+)["'`]/,
    );
    if (m?.[1]?.trim()) return { key: "bootstrap", url: m[1].trim() };
  }
  return null;
}

const resolved = resolveDatabaseUrl();
if (!resolved) {
  console.log(
    "[migrate] DATABASE_URL not set — skipping (the PGLite fallback migrates itself).",
  );
  process.exit(0);
}

console.log(`[migrate] using ${resolved.key} (value redacted)`);
const migrationsDir = join(root, "migrations");

async function main() {
  const pool = new pg.Pool({
    connectionString: resolved.url,
    max: 1,
    ssl: { rejectUnauthorized: false },
  });
  const client = await pool.connect();
  try {
    await client.query(
      "CREATE TABLE IF NOT EXISTS _migrations (name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())",
    );
    const applied = new Set(
      (await client.query("SELECT name FROM _migrations")).rows.map(
        (r) => r.name,
      ),
    );

    let files;
    try {
      files = (await readdir(migrationsDir))
        .filter((f) => f.endsWith(".sql"))
        .sort();
    } catch {
      console.log("[migrate] no migrations/ directory — nothing to do.");
      return;
    }

    let count = 0;
    for (const name of files) {
      if (applied.has(name)) continue;
      const text = await readFile(join(migrationsDir, name), "utf8");
      try {
        await client.query("BEGIN");
        await client.query(text);
        await client.query("INSERT INTO _migrations (name) VALUES ($1)", [
          name,
        ]);
        await client.query("COMMIT");
      } catch (err) {
        console.error(`[migrate] error applying ${name}`);
        try {
          await client.query("ROLLBACK");
        } catch {
          /* keep original */
        }
        throw err;
      }
      console.log(`[migrate] applied ${name}`);
      count += 1;
    }
    console.log(
      count
        ? `[migrate] done — ${count} migration(s) applied.`
        : "[migrate] done — already up to date.",
    );
  } finally {
    client.release();
    await pool.end();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
