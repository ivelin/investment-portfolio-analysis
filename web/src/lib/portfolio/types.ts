export type FundSeriesPoint = {
  asOfDate: string;
  liquidationValue: number;
  twrrIndex: number;
  dailyReturn: number | null;
};

export type PositionRow = {
  symbol: string;
  assetType: string | null;
  quantity: number;
  price: number | null;
  marketValue: number | null;
  weightPct: number | null;
};

export type AccountSummary = {
  id: string;
  broker: string;
  displayName: string;
  accountMask: string;
  fundSymbol: string;
  isDemo: boolean;
  /** True when this row came from in-app simulated import (not broker API). */
  isSimulated: boolean;
  currency: string;
  latestNlv: number | null;
  latestAsOf: string | null;
};

/**
 * Provenance of the numbers the dashboard is showing.
 * Computed server-side from connectors + account keys — never from ticker heuristics.
 */
export type DashboardDataMode = "sample" | "simulated" | "live";

export type WorkspaceSummary = {
  id: string;
  name: string;
  slug: string;
  plan: string;
  latestNlv: number | null;
  latestAsOf: string | null;
  twrrPeriodReturnPct: number | null;
  isDemo: boolean;
  accountCount: number;
  /** What the primary numbers represent. */
  dataMode: DashboardDataMode;
};

export type DashboardPayload = {
  workspace: WorkspaceSummary;
  accounts: AccountSummary[];
  series: FundSeriesPoint[];
  positions: PositionRow[];
  /** Account whose series/positions are currently loaded. */
  selectedAccountId: string | null;
  /** Same as workspace.dataMode — convenience for UI. */
  dataMode: DashboardDataMode;
};
