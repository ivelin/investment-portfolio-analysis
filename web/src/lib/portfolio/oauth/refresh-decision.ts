export const DEFAULT_REFRESH_SKEW_MS = 10 * 60 * 1000;

export type RefreshAction = "skip" | "refresh" | "needs_reauth";

export type TokenLike = {
  access_token?: string;
  refresh_token?: string;
  expires_at?: number | null;
} | null;

/**
 * MECE decision matrix for OAuth access-token refresh (pure, no I/O).
 */
export function classifyRefreshAction(
  tokens: TokenLike,
  opts: { force?: boolean; now?: number; skewMs?: number } = {},
): RefreshAction {
  const now = opts.now ?? Date.now();
  const skewMs = opts.skewMs ?? DEFAULT_REFRESH_SKEW_MS;
  if (!tokens || !tokens.access_token) return "needs_reauth";
  const expiresAt = tokens.expires_at;
  const nearExpiry =
    expiresAt == null || now >= Number(expiresAt) - skewMs;
  const due = Boolean(opts.force) || nearExpiry;
  if (!due) return "skip";
  if (!tokens.refresh_token) return "needs_reauth";
  return "refresh";
}
