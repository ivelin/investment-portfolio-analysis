import { createHash, createCipheriv, createDecipheriv, randomBytes } from "node:crypto";

type SecretPayload = Record<string, unknown>;

function material(): Buffer {
  const raw =
    process.env.CONNECTOR_SECRETS_KEY ||
    process.env.BETTER_AUTH_SECRET ||
    "dev-only-connector-secrets-key-change-me";
  return createHash("sha256").update(raw).digest();
}

/** Seal connector tokens / credentials. Never log the result. */
export function sealConnectorSecret(payload: SecretPayload): string {
  const key = material();
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const plaintext = Buffer.from(JSON.stringify(payload), "utf8");
  const enc = Buffer.concat([cipher.update(plaintext), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, enc]).toString("base64");
}

export function openConnectorSecret(ciphertext: string): SecretPayload {
  const buf = Buffer.from(ciphertext, "base64");
  const iv = buf.subarray(0, 12);
  const tag = buf.subarray(12, 28);
  const data = buf.subarray(28);
  const key = material();
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  const plain = Buffer.concat([decipher.update(data), decipher.final()]);
  return JSON.parse(plain.toString("utf8")) as SecretPayload;
}
