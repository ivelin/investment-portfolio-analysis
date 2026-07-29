const SENSITIVE_KEY =
  /^(password|secret|token|access_token|refresh_token|authorization|client_secret|code_verifier|ciphertext|api_key|apikey|bearer)$/i;

const SENSITIVE_VALUE =
  /postgres(ql)?:\/\/\S+|Bearer\s+\S+|sk-[A-Za-z0-9]{10,}|pa_[A-Za-z0-9]{16,}/gi;

export function redactText(input: string): string {
  return input
    .replace(SENSITIVE_VALUE, "[redacted]")
    .replace(/client_secret=[^&\s]+/gi, "client_secret=[redacted]");
}

export function redactObject<T>(value: T): T {
  return walk(value) as T;
}

function walk(value: unknown): unknown {
  if (value == null) return value;
  if (typeof value === "string") return redactText(value);
  if (typeof value !== "object") return value;
  if (Array.isArray(value)) return value.map(walk);
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
    if (SENSITIVE_KEY.test(k)) {
      out[k] = "[redacted]";
      continue;
    }
    out[k] = walk(v);
  }
  return out;
}

export function auditMeta(meta: Record<string, unknown>): Record<string, unknown> {
  return redactObject(meta) as Record<string, unknown>;
}
