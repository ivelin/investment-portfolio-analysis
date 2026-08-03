/**
 * Data freshness + source health for broker-backed portfolio views.
 * Pure helpers — no I/O. UI and service layer use these for banners/CTAs.
 */

import { isReauthErrorMessage } from "./brokers/sync-errors";

export type DataFreshness =
  | "demo"
  | "live_fresh"
  | "live_stale"
  | "live_frozen"
  | "live_degraded"
  | "missing";

export type SourceHealth =
  | "ok"
  | "reauth_required"
  | "transient_error"
  | "contract_mismatch"
  | "disconnected"
  | "unknown";

/** Hours after last good as-of before we label holdings "stale". */
export const STALE_AFTER_HOURS = 36;

/** Hours after which we treat series as frozen (last-known-good only). */
export const FROZEN_AFTER_HOURS = 24 * 7;

export function parseAsOfMs(asOf: string | null | undefined): number | null {
  if (!asOf) return null;
  // YYYY-MM-DD → UTC noon to avoid TZ edge
  if (/^\d{4}-\d{2}-\d{2}$/.test(asOf)) {
    const t = Date.parse(`${asOf}T12:00:00.000Z`);
    return Number.isFinite(t) ? t : null;
  }
  const t = Date.parse(asOf);
  return Number.isFinite(t) ? t : null;
}

export function hoursSince(
  asOf: string | null | undefined,
  nowMs = Date.now(),
): number | null {
  const t = parseAsOfMs(asOf);
  if (t == null) return null;
  return (nowMs - t) / (1000 * 60 * 60);
}

export function classifySourceHealth(args: {
  connectorStatus?: string | null;
  lastError?: string | null;
}): SourceHealth {
  const status = (args.connectorStatus || "").toLowerCase();
  const err = args.lastError || "";
  if (status === "disconnected" || status === "") return "disconnected";
  if (status === "pending_oauth") return "disconnected";
  if (/contract|schema|format|unparseable|unsupported.?payload/i.test(err)) {
    return "contract_mismatch";
  }
  if (
    status === "error" ||
    status === "needs_reauth" ||
    isReauthErrorMessage(err)
  ) {
    if (isReauthErrorMessage(err) || status === "needs_reauth") {
      return "reauth_required";
    }
    return "transient_error";
  }
  if (status === "connected") {
    if (err) return "transient_error";
    return "ok";
  }
  return "unknown";
}

export function classifyDataFreshness(args: {
  isDemo: boolean;
  latestAsOf: string | null | undefined;
  sourceHealth: SourceHealth;
  hasLiveAccounts: boolean;
  nowMs?: number;
}): DataFreshness {
  if (args.isDemo && !args.hasLiveAccounts) return "demo";
  if (!args.hasLiveAccounts) return "missing";

  if (
    args.sourceHealth === "reauth_required" ||
    args.sourceHealth === "contract_mismatch"
  ) {
    return args.latestAsOf ? "live_frozen" : "live_degraded";
  }
  if (args.sourceHealth === "transient_error") {
    return args.latestAsOf ? "live_stale" : "live_degraded";
  }

  const hours = hoursSince(args.latestAsOf, args.nowMs);
  if (hours == null) return "live_degraded";
  if (hours > FROZEN_AFTER_HOURS) return "live_frozen";
  if (hours > STALE_AFTER_HOURS) return "live_stale";
  return "live_fresh";
}

export type DataHealthSummary = {
  freshness: DataFreshness;
  sourceHealth: SourceHealth;
  /** Safe to show NLV/returns as "current" */
  trustLiveNumbers: boolean;
  /** Show last-known-good banner */
  showStaleBanner: boolean;
  /** User must reconnect OAuth */
  needsReauth: boolean;
  /** API shape drift — do not overwrite local last-good */
  contractIssue: boolean;
  message: string | null;
  cta: "none" | "reconnect" | "retry_sync" | "connect";
};

export function buildDataHealthSummary(args: {
  isDemo: boolean;
  hasLiveAccounts: boolean;
  latestAsOf: string | null | undefined;
  connectorStatus?: string | null;
  lastError?: string | null;
  nlvComplete?: boolean;
  nowMs?: number;
}): DataHealthSummary {
  const sourceHealth = classifySourceHealth({
    connectorStatus: args.connectorStatus,
    lastError: args.lastError,
  });
  const freshness = classifyDataFreshness({
    isDemo: args.isDemo,
    latestAsOf: args.latestAsOf,
    sourceHealth,
    hasLiveAccounts: args.hasLiveAccounts,
    nowMs: args.nowMs,
  });

  const needsReauth = sourceHealth === "reauth_required";
  const contractIssue = sourceHealth === "contract_mismatch";
  const showStaleBanner =
    freshness === "live_stale" ||
    freshness === "live_frozen" ||
    freshness === "live_degraded" ||
    needsReauth ||
    contractIssue ||
    args.nlvComplete === false;

  const trustLiveNumbers =
    (freshness === "live_fresh" || freshness === "demo") &&
    !needsReauth &&
    !contractIssue &&
    args.nlvComplete !== false;

  let message: string | null = null;
  let cta: DataHealthSummary["cta"] = "none";

  if (freshness === "demo") {
    message = null;
    cta = "connect";
  } else if (needsReauth) {
    message =
      "Broker authorization expired. Showing last saved holdings — figures may be outdated. Reconnect to refresh.";
    cta = "reconnect";
  } else if (contractIssue) {
    message =
      "Broker sent data in an unexpected format. Last good snapshot is preserved; we did not overwrite your books.";
    cta = "retry_sync";
  } else if (freshness === "live_frozen") {
    message =
      "Holdings are frozen on the last successful sync. Numbers are historical until the broker connection recovers.";
    cta = sourceHealth === "transient_error" ? "retry_sync" : "reconnect";
  } else if (freshness === "live_stale") {
    message =
      "Broker data is older than usual. Showing last known values until the next successful sync.";
    cta = "retry_sync";
  } else if (freshness === "live_degraded") {
    message =
      "Live accounts are linked but some balances are incomplete. Incomplete figures are not treated as zero.";
    cta = "retry_sync";
  } else if (args.nlvComplete === false) {
    message =
      "Some account balances are missing; totals only include accounts with known liquidation values.";
    cta = "retry_sync";
  }

  return {
    freshness,
    sourceHealth,
    trustLiveNumbers,
    showStaleBanner,
    needsReauth,
    contractIssue,
    message,
    cta,
  };
}
