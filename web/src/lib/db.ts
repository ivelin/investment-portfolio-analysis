import { resolveDatabaseUrl } from "./db-url";
import { pgliteUsableInThisRuntime } from "./runtime-env";

/** Which database backend is active. */
export type DbSource = "neon" | "pglite";

// An empty/whitespace DATABASE_URL (an easy misconfig in deploy UIs) must mean
// "unset" — otherwise production would silently run on the PGLite fallback.
// Also accept common Postgres/Neon marketplace aliases + publish bootstrap
// (see db-url.ts).
const databaseUrl = resolveDatabaseUrl();

/**
 * Active backend: real **Neon** when `DATABASE_URL` (or alias / bootstrap) is set
 * (deployed), otherwise a local embedded **PGLite** so the app has a working
 * database in the live preview.
 *
 * On serverless (Vercel) without a URL, we still report `pglite` as the *intent*
 * but refuse to boot PGLite — it cannot persist and the WASM assets 500.
 */
export const dbSource: DbSource = databaseUrl ? "neon" : "pglite";

/**
 * Minimal shared SQL surface, satisfied by both Neon and PGLite. Both the
 * tagged-template and `.query()` forms resolve to an array of row objects:
 *
 *   const sql = await getSql();
 *   const rows = await sql`select * from todos where id = ${id}`; // parameterized
 *   const rows2 = await sql.query("select * from todos where id = $1", [id]);
 */
export interface Sql {
  <T = Record<string, unknown>>(
    strings: TemplateStringsArray,
    ...values: unknown[]
  ): Promise<T[]>;
  query<T = Record<string, unknown>>(
    text: string,
    params?: unknown[]
  ): Promise<T[]>;
}

/**
 * Init state lives on globalThis as promises: dev HMR creates new instances of
 * this module, and two instances racing module-level state would open a second
 * pool or run two concurrent PGLite migration passes (whose duplicate
 * `_migrations` insert rejects — and would get memoized, poisoning every later
 * `getSql()`). A failed init clears its slot so the next call retries.
 */
const globalRef = globalThis as typeof globalThis & {
  __pgSqlPromise__?: Promise<Sql>;
  __pgPoolPromise__?: Promise<import("pg").Pool>;
  __neonMigratePromise__?: Promise<void>;
  __neonRekeyPromise__?: Promise<void>;
  __pgliteInstance__?: Promise<import("@electric-sql/pglite").PGlite>;
  __pgliteMigrateChain__?: Promise<void>;
};

/**
 * Result-type parity: Postgres sends every value as text plus a type OID — the
 * JS value is the DRIVER's parsing choice, and pg and PGLite disagree (pg:
 * int8 -> string, date -> local-midnight Date; PGLite: int8 -> BigInt, which
 * JSON.stringify rejects, date -> UTC Date). Normalize both so preview and
 * production return identical, JSON-safe shapes:
 *   int8/bigint (incl. count(*)) -> number (past 2^53 loses precision — cast
 *                                   `::text` if you ever need huge integers)
 *   date                         -> 'YYYY-MM-DD' string
 *   interval                     -> Postgres interval text
 * numeric already comes back as a string on both (arbitrary precision).
 */
const OID_INT8 = 20;
const OID_DATE = 1082;
const OID_INTERVAL = 1186;
const identity = (v: string) => v;

type Run = <T>(text: string, params: unknown[]) => Promise<T[]>;

/** Bundle migrations/*.sql (same source as scripts/migrate.mjs + PGLite). */
function loadMigrationFiles(): Array<{ name: string; text: string }> {
  const migrations = import.meta.glob("/migrations/*.sql", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;
  return Object.entries(migrations)
    .map(([path, text]) => ({
      name: path.split("/").pop()!,
      text: String(text),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function toSql(run: Run): Sql {
  const sql = (async <T = Record<string, unknown>>(
    strings: TemplateStringsArray,
    ...values: unknown[]
  ): Promise<T[]> => {
    let text = "";
    const params: unknown[] = [];
    strings.forEach((part, i) => {
      text += part;
      if (i < values.length) {
        params.push(values[i]);
        text += `$${params.length}`;
      }
    });
    return run<T>(text, params);
  }) as Sql;
  sql.query = async <T = Record<string, unknown>>(
    text: string,
    params: unknown[] = [],
  ) => run<T>(text, params);
  return sql;
}

async function applyNeonMigrations(pool: import("pg").Pool): Promise<void> {
  await pool.query(`
    create table if not exists _migrations (
      name text primary key,
      applied_at timestamptz not null default now()
    )
  `);
  const doneRes = await pool.query<{ name: string }>(
    "select name from _migrations",
  );
  const done = new Set(doneRes.rows.map((r) => r.name));
  for (const { name, text } of loadMigrationFiles()) {
    if (done.has(name)) continue;
    const client = await pool.connect();
    try {
      await client.query("begin");
      await client.query(text);
      await client.query("insert into _migrations (name) values ($1)", [name]);
      await client.query("commit");
    } catch (err) {
      await client.query("rollback");
      throw err;
    } finally {
      client.release();
    }
  }
}

/**
 * Shared Neon / Postgres pool for app SQL + Better Auth. Serverless-friendly
 * (max 1 connection per isolate). Migrations run once per process before the
 * pool is handed out.
 */
export function getPgPool(): Promise<import("pg").Pool> {
  // Re-resolve so publish bootstrap is picked up if env/module order varies.
  const url = resolveDatabaseUrl() ?? databaseUrl;
  if (!url) {
    return Promise.reject(
      new Error(
        "getPgPool() requires DATABASE_URL or publish bootstrap. Use getPglite() in preview.",
      ),
    );
  }
  globalRef.__pgPoolPromise__ ??= (async () => {
    const { Pool, types } = await import("pg");
    types.setTypeParser(OID_INT8, Number);
    types.setTypeParser(OID_DATE, identity);
    types.setTypeParser(OID_INTERVAL, identity);
    // Neon pooled endpoint + Vercel serverless: one client per isolate.
    // Explicit ssl helps when connection string sslmode is rewritten by hosts.
    const pool = new Pool({
      connectionString: url,
      max: 1,
      idleTimeoutMillis: 10_000,
      connectionTimeoutMillis: 15_000,
      allowExitOnIdle: true,
      ssl: { rejectUnauthorized: false },
    });
    globalRef.__neonMigratePromise__ ??= applyNeonMigrations(pool).catch(
      (err) => {
        globalRef.__neonMigratePromise__ = undefined;
        throw err;
      },
    );
    await globalRef.__neonMigratePromise__;

    // Best-effort re-key of connector secrets under bootstrap-derived material
    // so the agent sandbox can open the same tokens after one prod boot.
    globalRef.__neonRekeyPromise__ ??= (async () => {
      try {
        const { rekeyConnectorSecretsIfNeeded } = await import(
          "./portfolio/oauth/secrets.server"
        );
        const sql = toSql(async <T>(text: string, params: unknown[]) => {
          const res = await pool.query(text, params);
          return res.rows as T[];
        });
        const result = await rekeyConnectorSecretsIfNeeded(sql);
        if (result.rekeyed > 0) {
          console.info(
            `[db] re-sealed ${result.rekeyed}/${result.checked} connector secret(s) under preferred key`,
          );
        }
      } catch (err) {
        console.warn(
          "[db] connector secret re-key skipped:",
          err instanceof Error ? err.message : err,
        );
      }
    })();
    // Don't block requests on re-key; fire and forget after migrate.
    void globalRef.__neonRekeyPromise__;

    return pool;
  })().catch((err) => {
    globalRef.__pgPoolPromise__ = undefined;
    throw err;
  });
  return globalRef.__pgPoolPromise__;
}

function createNeonSql(): Promise<Sql> {
  globalRef.__pgSqlPromise__ ??= (async () => {
    const pool = await getPgPool();
    return toSql(async <T>(text: string, params: unknown[]) => {
      const res = await pool.query(text, params);
      return res.rows as T[];
    });
  })().catch((err) => {
    globalRef.__pgSqlPromise__ = undefined;
    throw err;
  });
  return globalRef.__pgSqlPromise__;
}

async function createPgliteSql(): Promise<Sql> {
  // Fail closed on serverless: PGLite WASM assets are not available under
  // /var/task and in-memory state cannot span OAuth redirects across isolates.
  if (!pgliteUsableInThisRuntime()) {
    throw new Error(
      "No DATABASE_URL on serverless deploy. Published sign-in requires Postgres. " +
        "PGLite is only for the live preview / local dev server.",
    );
  }

  globalRef.__pgliteInstance__ ??= (async () => {
    const { PGlite } = await import("@electric-sql/pglite");
    // Disk-backed only when explicitly enabled (live preview). Tests stay in-memory.
    // Never Neon; path is under gitignored data/.
    const dataDir =
      process.env.PGLITE_DATA_DIR?.trim() ||
      (process.env.GROK_PREVIEW_PERSIST === "1"
        ? "/workspace/data/pglite"
        : undefined);

    const parsers = {
      [OID_INT8]: Number,
      [OID_DATE]: identity,
      [OID_INTERVAL]: identity,
    };
    const pg = dataDir
      ? new PGlite(dataDir, { parsers })
      : new PGlite({ parsers });
    await pg.exec(`
      create table if not exists _migrations (
        name text primary key,
        applied_at timestamptz not null default now()
      )
    `);
    return pg;
  })().catch((err) => {
    globalRef.__pgliteInstance__ = undefined;
    throw err;
  });
  const pg = await globalRef.__pgliteInstance__;

  const migrate = async (): Promise<void> => {
    const doneRows = await pg.query<{ name: string }>(
      "select name from _migrations",
    );
    const done = new Set(doneRows.rows.map((r) => r.name));
    for (const { name, text } of loadMigrationFiles()) {
      if (done.has(name)) continue;
      await pg.transaction(async (tx) => {
        await tx.exec(text);
        await tx.query("insert into _migrations (name) values ($1)", [name]);
      });
    }
  };
  const pass = (globalRef.__pgliteMigrateChain__ ?? Promise.resolve())
    .catch(() => undefined)
    .then(migrate);
  globalRef.__pgliteMigrateChain__ = pass;
  await pass;

  return toSql(async <T>(text: string, params: unknown[]) => {
    const result = await pg.query<T>(text, params);
    return result.rows;
  });
}

let sqlPromise: Promise<Sql> | null = null;

async function createSql(): Promise<Sql> {
  if (typeof window !== "undefined") {
    throw new Error(
      "@/lib/db is server-only — call getSql() from a createServerFn handler " +
        "or a server route loader, never from client code.",
    );
  }
  const url = resolveDatabaseUrl() ?? databaseUrl;
  return url ? createNeonSql() : createPgliteSql();
}

/**
 * Get the shared, **server-only** SQL client. Neon when `DATABASE_URL` / bootstrap
 * is set, otherwise the local PGLite fallback. Memoized — safe to call per request.
 */
export function getSql(): Promise<Sql> {
  sqlPromise ??= createSql().catch((err) => {
    sqlPromise = null;
    throw err;
  });
  return sqlPromise;
}

export async function ensureDbReady(): Promise<void> {
  await getSql();
}

export async function getPglite(): Promise<import("@electric-sql/pglite").PGlite> {
  if (resolveDatabaseUrl() ?? databaseUrl) {
    throw new Error(
      "getPglite() is only available on the PGLite fallback (no DATABASE_URL)",
    );
  }
  if (!pgliteUsableInThisRuntime()) {
    throw new Error(
      "getPglite() unavailable on serverless without DATABASE_URL",
    );
  }
  await createPgliteSql();
  const pg = await globalRef.__pgliteInstance__;
  if (!pg) throw new Error("PGLite failed to initialize");
  return pg;
}

// Kick bootstrap on import (preview PGLite migrations / neon readiness).
const globalBoot = globalThis as typeof globalThis & {
  __pgBootstrapPromise__?: Promise<void>;
};
globalBoot.__pgBootstrapPromise__ ??= ensureDbReady().catch((err) => {
  globalBoot.__pgBootstrapPromise__ = undefined;
  console.error("[db] bootstrap failed:", err);
  throw err;
});
