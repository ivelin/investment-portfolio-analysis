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
  currency: string;
  latestNlv: number | null;
  latestAsOf: string | null;
};

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
};

export type DashboardPayload = {
  workspace: WorkspaceSummary;
  accounts: AccountSummary[];
  series: FundSeriesPoint[];
  positions: PositionRow[];
  /** Account whose series/positions are currently loaded. */
  selectedAccountId: string | null;
};
