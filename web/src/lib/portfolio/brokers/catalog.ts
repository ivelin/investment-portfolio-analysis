export const BROKER_IDS = [
  "schwab",
  "robinhood",
  "ibkr",
  "fidelity",
  "synthetic",
] as const;

export type BrokerId = (typeof BROKER_IDS)[number];

/**
 * HARD RULE: connectors are analysis-only. `capabilities` never includes trade.
 * Enforced at runtime by read-only-policy + brokerFetch; CI scans for writes.
 */
export type BrokerCapability = "read_portfolio" | "oauth";

export type BrokerDef = {
  id: BrokerId;
  label: string;
  authKind: "direct_oauth" | "remote_mcp" | "exports_only";
  /** Always read-only for this product. */
  accessMode: "read_only_analysis";
  capabilities: readonly BrokerCapability[];
  mcpUrl?: string | null;
  docsUrl?: string;
  setupPath: boolean;
};

export const BROKERS: Record<BrokerId, BrokerDef> = {
  schwab: {
    id: "schwab",
    label: "Charles Schwab",
    authKind: "direct_oauth",
    accessMode: "read_only_analysis",
    capabilities: ["oauth", "read_portfolio"],
    docsUrl: "https://developer.schwab.com/",
    setupPath: true,
  },
  robinhood: {
    id: "robinhood",
    label: "Robinhood",
    authKind: "remote_mcp",
    accessMode: "read_only_analysis",
    // OAuth only today — no MCP tool calls (and never place/cancel order tools).
    capabilities: ["oauth"],
    mcpUrl: "https://agent.robinhood.com/mcp/trading",
    docsUrl:
      "https://robinhood.com/us/en/support/articles/agentic-trading-overview/",
    setupPath: true,
  },
  ibkr: {
    id: "ibkr",
    label: "Interactive Brokers",
    authKind: "remote_mcp",
    accessMode: "read_only_analysis",
    capabilities: ["oauth"],
    mcpUrl: "https://api.ibkr.com/v1/api/mcp-public",
    docsUrl: "https://www.interactivebrokers.com/en/trading/ai-integrations.php",
    setupPath: true,
  },
  fidelity: {
    id: "fidelity",
    label: "Fidelity",
    authKind: "exports_only",
    accessMode: "read_only_analysis",
    capabilities: [],
    setupPath: true,
  },
  synthetic: {
    id: "synthetic",
    label: "Sample fund",
    authKind: "exports_only",
    accessMode: "read_only_analysis",
    capabilities: [],
    setupPath: false,
  },
};

export function isBrokerId(v: string): v is BrokerId {
  return (BROKER_IDS as readonly string[]).includes(v);
}
