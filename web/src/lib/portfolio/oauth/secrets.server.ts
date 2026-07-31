import {
  createHash,
  createCipheriv,
  createDecipheriv,
  randomBytes,
} from "node:crypto";

type SecretPayload = Record<string, unknown>;

/**
 * Key ring for connector token encryption.
 *
 * Prefer (in order for sealing):
 *  1. CONNECTOR_SECRETS_KEY env
 *  2. Stable key derived from publish bootstrap DATABASE_URL (prod serverless
 *     only — preview never loads that DB)
 *  3. BETTER_AUTH_SECRET
 *  4. Dev fallback (isolated PGLite preview)
 *
 * Open tries every candidate so older ciphertexts keep working after re-key.
 * Preview/CI stay on PGLite with the dev fallback; prod never shares that DB.
 */
function bootstrapDerivedKeyMaterial(): string | undefined {
  try {
    const mods = import.meta.glob("../../db-bootstrap.secret.ts", {
      eager: true,
    }) as Record<string, { BOOTSTRAP_DATABASE_URL?: string }>;
    for (const mod of Object.values(mods)) {
      const url = mod.BOOTSTRAP_DATABASE_URL?.trim();
      if (url) return `bootstrap-connector-v1:${url}`;
    }
  } catch {
    /* no bootstrap */
  }
  return undefined;
}

function candidateMaterials(): string[] {
  const out: string[] = [];
  const push = (v: string | undefined | null) => {
    const t = v?.trim();
    if (t && !out.includes(t)) out.push(t);
  };
  push(process.env.CONNECTOR_SECRETS_KEY);
  // Only useful on serverless publish (preview ignores bootstrap DB entirely).
  push(bootstrapDerivedKeyMaterial());
  push(process.env.BETTER_AUTH_SECRET);
  push("dev-only-connector-secrets-key-change-me");
  return out;
}

function preferredMaterial(): string {
  return candidateMaterials()[0]!;
}

function materialBuffer(raw: string): Buffer {
  return createHash("sha256").update(raw).digest();
}

function sealWith(rawKey: string, payload: SecretPayload): string {
  const key = materialBuffer(rawKey);
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const plaintext = Buffer.from(JSON.stringify(payload), "utf8");
  const enc = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, enc]).toString("base64");
}

function openWith(rawKey: string, ciphertext: string): SecretPayload {
  const buf = Buffer.from(ciphertext, "base64");
  const iv = buf.subarray(0, 12);
  const tag = buf.subarray(12, 28);
  const data = buf.subarray(28);
  const decipher = createDecipheriv("aes-256-gcm", materialBuffer(rawKey), iv);
  decipher.setAuthTag(tag);
  const plain = Buffer.concat([decipher.update(data), decipher.final()]);
  return JSON.parse(plain.toString("utf8")) as SecretPayload;
}

/** Seal connector tokens / credentials. Never log the result. */
export function sealConnectorSecret(payload: SecretPayload): string {
  return sealWith(preferredMaterial(), payload);
}

export function openConnectorSecret(ciphertext: string): SecretPayload {
  let lastErr: unknown;
  for (const raw of candidateMaterials()) {
    try {
      return openWith(raw, ciphertext);
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr instanceof Error
    ? lastErr
    : new Error("Cannot decrypt connector secret");
}

/**
 * Re-seal every connector_secrets row under the preferred key when we can
 * open it with any key on the ring. Safe to call repeatedly (idempotent).
 * Runs on published Neon only — never against preview PGLite.
 */
export async function rekeyConnectorSecretsIfNeeded(
  sql: {
    <T = Record<string, unknown>>(
      strings: TemplateStringsArray,
      ...values: unknown[]
    ): Promise<T[]>;
  },
): Promise<{ checked: number; rekeyed: number }> {
  const rows = await sql<{
    connector_id: string;
    tenant_id: string;
    ciphertext: string;
  }>`
    select connector_id, tenant_id, ciphertext from connector_secrets
  `;
  let rekeyed = 0;
  const preferred = preferredMaterial();
  for (const row of rows) {
    try {
      const payload = openConnectorSecret(row.ciphertext);
      const next = sealWith(preferred, payload);
      if (next === row.ciphertext) continue;
      openWith(preferred, next);
      await sql`
        update connector_secrets set
          ciphertext = ${next},
          updated_at = now()
        where connector_id = ${row.connector_id}
          and tenant_id = ${row.tenant_id}
      `;
      rekeyed += 1;
    } catch {
      /* leave row */
    }
  }
  return { checked: rows.length, rekeyed };
}
