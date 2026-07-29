export const BROKER_IDS = [
  "schwab",
  "robinhood",
  "ibkr",
  "fidelity",
  "synthetic",
] as const;

export type BrokerId = (typeof BROKER_IDS)[number];

export type BrokerDef = {
  id: BrokerId;
  label: string;
  authKind: "direct_oauth" | "remote_mcp" | "exports_only";
  mcpUrl?: string | null;
  docsUrl?: string;
  setupPath: boolean;
};

export const BROKERS: Record<BrokerId, BrokerDef> = {
  schwab: {
    id: "schwab",
    label: "Charles Schwab",
    authKind: "direct_oauth",
    docsUrl: "https://developer.schwab.com/",
    setupPath: true,
  },
  robinhood: {
    id: "robinhood",
    label: "Robinhood",
    authKind: "remote_mcp",
    mcpUrl: null,
    setupPath: true,
  },
  ibkr: {
    id: "ibkr",
    label: "Interactive Brokers",
    authKind: "remote_mcp",
    mcpUrl: null,
    setupPath: true,
  },
  fidelity: {
    id: "fidelity",
    label: "Fidelity",
    authKind: "exports_only",
    setupPath: true,
  },
  synthetic: {
    id: "synthetic",
    label: "Sample fund",
    authKind: "exports_only",
    setupPath: false,
  },
};

export function isBrokerId(v: string): v is BrokerId {
  return (BROKER_IDS as readonly string[]).includes(v);
}
