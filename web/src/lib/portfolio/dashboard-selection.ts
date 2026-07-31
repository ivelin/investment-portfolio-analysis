/**
 * Pure dashboard account selection — demo vs live broker data.
 * Used by getDashboardPayload and unit-tested without DB.
 */

export type SelectableAccount = {
  id: string;
  isDemo: boolean;
  latestNlv?: number | null;
};

/**
 * Primary account for chart/positions.
 * Prefer live (non-demo) accounts so sample data never shadows broker data.
 */
export function pickPrimaryAccount<T extends SelectableAccount>(
  accounts: readonly T[],
  preferredAccountId?: string | null,
): T | null {
  if (!accounts.length) return null;
  const live = accounts.filter((a) => !a.isDemo);
  if (preferredAccountId) {
    const preferred = accounts.find((a) => a.id === preferredAccountId);
    // Allow selecting sample only when no live accounts exist.
    if (preferred) {
      if (!preferred.isDemo || live.length === 0) return preferred;
    }
  }
  return live[0] ?? accounts[0] ?? null;
}

/** Account chips: hide sample once any live broker account exists. */
export function visibleDashboardAccounts<T extends SelectableAccount>(
  accounts: readonly T[],
): T[] {
  const live = accounts.filter((a) => !a.isDemo);
  return live.length > 0 ? live : [...accounts];
}

export function workspaceIsDemoOnly(
  accounts: readonly SelectableAccount[],
): boolean {
  return accounts.every((a) => a.isDemo);
}

/** Demo symbols that must not appear as "live" holdings. */
export const DEMO_HOLDING_SYMBOLS = [
  "AAPL",
  "MSFT",
  "NVDA",
  "VOO",
  "CASH",
] as const;

/** Simulated Schwab holdings — deliberately distinct from demo. */
export const SIMULATED_SCHWAB_SYMBOLS = [
  "SGOV",
  "TSLA",
  "IBIT",
  "SCHD",
  "VXUS",
  "BND",
] as const;

export function positionsLookLikeDemo(
  symbols: readonly string[],
): boolean {
  if (!symbols.length) return false;
  const set = new Set(symbols.map((s) => s.toUpperCase()));
  const demoHits = DEMO_HOLDING_SYMBOLS.filter((s) => set.has(s)).length;
  return demoHits >= 3 && set.size <= DEMO_HOLDING_SYMBOLS.length + 1;
}

export function positionsLookLikeSimulatedSchwab(
  symbols: readonly string[],
): boolean {
  if (!symbols.length) return false;
  const set = new Set(symbols.map((s) => s.toUpperCase()));
  return SIMULATED_SCHWAB_SYMBOLS.some((s) => set.has(s));
}
