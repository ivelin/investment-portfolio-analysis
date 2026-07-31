/**
 * Pure dashboard account selection — demo vs simulated vs live broker data.
 * Used by getDashboardPayload and unit-tested without DB.
 *
 * HARD RULE: never label "simulated" from ticker symbols alone.
 * Real Schwab books commonly hold SGOV/TSLA/IBIT; ticker heuristics false-positive.
 */

export type SelectableAccount = {
  id: string;
  isDemo: boolean;
  isSimulated?: boolean;
  latestNlv?: number | null;
};

export type DashboardDataMode = "sample" | "simulated" | "live";

/**
 * Primary account for chart/positions.
 * Prefer live (non-demo) accounts so sample data never shadows broker data.
 * Prefer non-simulated live when both simulated and real live exist.
 */
export function pickPrimaryAccount<
  T extends SelectableAccount,
>(accounts: readonly T[], preferredAccountId?: string | null): T | null {
  if (!accounts.length) return null;
  const live = accounts.filter((a) => !a.isDemo);
  const realLive = live.filter((a) => !a.isSimulated);
  const pool = realLive.length > 0 ? realLive : live;

  if (preferredAccountId) {
    const preferred = accounts.find((a) => a.id === preferredAccountId);
    if (preferred) {
      if (!preferred.isDemo || live.length === 0) {
        if (preferred.isSimulated && realLive.length > 0) {
          return realLive[0] ?? preferred;
        }
        return preferred;
      }
    }
  }
  return pool[0] ?? accounts[0] ?? null;
}

/** Account chips: hide sample once any live broker account exists. */
export function visibleDashboardAccounts<
  T extends SelectableAccount,
>(accounts: readonly T[]): T[] {
  const live = accounts.filter((a) => !a.isDemo);
  if (live.length === 0) return [...accounts];
  const realLive = live.filter((a) => !a.isSimulated);
  // When real broker data exists, never show simulated chips alongside it.
  return realLive.length > 0 ? realLive : live;
}

export function workspaceIsDemoOnly(
  accounts: readonly SelectableAccount[],
): boolean {
  return accounts.every((a) => a.isDemo);
}

/**
 * Server/UI single source of truth for what the dashboard numbers mean.
 * Priority: live OAuth/API > simulated import > sample only.
 */
export function resolveDashboardDataMode(args: {
  accounts: readonly SelectableAccount[];
  /** Connector modes for this tenant (e.g. direct_oauth, simulated, mcp_snapshot). */
  connectorModes?: readonly string[];
}): DashboardDataMode {
  const live = args.accounts.filter((a) => !a.isDemo);
  if (live.length === 0) return "sample";

  const modes = args.connectorModes ?? [];
  const hasLiveConnector = modes.some(
    (m) =>
      m === "direct_oauth" ||
      m === "remote_mcp" ||
      m === "mcp_snapshot" ||
      m === "oauth",
  );
  const hasSimConnector = modes.includes("simulated");
  const realLive = live.filter((a) => !a.isSimulated);
  const onlySim = live.length > 0 && realLive.length === 0;

  if (hasLiveConnector || realLive.length > 0) return "live";
  if (hasSimConnector || onlySim) return "simulated";
  return "live";
}

/** Demo symbols that must not appear as "live" holdings. */
export const DEMO_HOLDING_SYMBOLS = [
  "AAPL",
  "MSFT",
  "NVDA",
  "VOO",
  "CASH",
] as const;

/** Simulated Schwab seed symbols — for tests / seed only, NOT UI labeling. */
export const SIMULATED_SCHWAB_SYMBOLS = [
  "SGOV",
  "TSLA",
  "IBIT",
  "SCHD",
  "VXUS",
  "BND",
] as const;

export function positionsLookLikeDemo(symbols: readonly string[]): boolean {
  if (!symbols.length) return false;
  const set = new Set(symbols.map((s) => s.toUpperCase()));
  const demoHits = DEMO_HOLDING_SYMBOLS.filter((s) => set.has(s)).length;
  return demoHits >= 3 && set.size <= DEMO_HOLDING_SYMBOLS.length + 1;
}

/**
 * @deprecated Do not use for UI labels — real portfolios hold SGOV/TSLA/IBIT.
 * Kept only for narrow test assertions on the fixed sim seed book.
 */
export function positionsLookLikeSimulatedSchwab(
  symbols: readonly string[],
): boolean {
  if (!symbols.length) return false;
  const set = new Set(symbols.map((s) => s.toUpperCase()));
  const hits = SIMULATED_SCHWAB_SYMBOLS.filter((s) => set.has(s)).length;
  // Stricter: require ≥3 sim-seed symbols and a small book (the fixed seed).
  return hits >= 3 && set.size <= SIMULATED_SCHWAB_SYMBOLS.length + 2;
}

/** Detect simulated account rows from key / display name conventions. */
export function isSimulatedAccountRow(args: {
  accountKey?: string | null;
  displayName?: string | null;
}): boolean {
  const key = args.accountKey ?? "";
  const name = args.displayName ?? "";
  return key.startsWith("sim_") || /\(sim\)/i.test(name);
}
