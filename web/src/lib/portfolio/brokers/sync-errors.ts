/**
 * Classify broker sync/OAuth errors (pure).
 * Keep accounts + last-known-good data on reauth/transient failures.
 */

export type SyncFailureClass =
  | "reauth"
  | "transient"
  | "contract"
  | "not_connected"
  | "unknown";

/** True when the user must complete OAuth again (tokens unusable). */
export function isReauthErrorMessage(msg: string): boolean {
  return /re-?auth|invalid_grant|token.*(expired|revoked|invalid)|401|unauthorized|not connected|no (access|refresh) token|consent required|login.?required|access.?denied/i.test(
    msg,
  );
}

export function isContractErrorMessage(msg: string): boolean {
  return /contract|schema|format.?change|unparseable|unsupported.?payload|unexpected.?shape|version.?mismatch|empty.?account.?list.?after.?parse/i.test(
    msg,
  );
}

export function isTransientErrorMessage(msg: string): boolean {
  return /timeout|network|econnreset|enotfound|429|rate.?limit|502|503|504|temporarily|try again|fetch failed/i.test(
    msg,
  );
}

export function classifySyncFailure(msg: string): SyncFailureClass {
  if (!msg) return "unknown";
  if (/not connected|no tokens/i.test(msg) && !isReauthErrorMessage(msg)) {
    return "not_connected";
  }
  if (isContractErrorMessage(msg)) return "contract";
  if (isReauthErrorMessage(msg)) return "reauth";
  if (isTransientErrorMessage(msg)) return "transient";
  return "unknown";
}

/** DB connector status after a failed sync — never "disconnected" if secrets remain. */
export function connectorStatusAfterSyncFailure(
  failure: SyncFailureClass,
): "error" | "needs_reauth" | "connected" {
  if (failure === "reauth") return "needs_reauth";
  if (failure === "contract") return "error";
  if (failure === "transient") return "error";
  if (failure === "not_connected") return "error";
  return "error";
}

export function userMessageForSyncFailure(
  failure: SyncFailureClass,
  raw: string,
): string {
  switch (failure) {
    case "reauth":
      return "Re-authorization required — last holdings kept until you reconnect.";
    case "contract":
      return "Broker API response format was not recognized — last holdings kept.";
    case "transient":
      return "Temporary broker connectivity issue — last holdings kept. Retry soon.";
    case "not_connected":
      return "Broker is not connected.";
    default:
      return raw.slice(0, 400) || "Sync failed — last holdings kept.";
  }
}
