/**
 * HARD ARCHITECTURE RULE
 * ──────────────────────
 * Broker connectors are **read-only analysis only**.
 *
 * This app may:
 *   • OAuth / token refresh (auth plumbing)
 *   • Read accounts, balances, positions, transactions history (for analysis)
 *
 * This app must NEVER:
 *   • Place, preview, cancel, or replace orders
 *   • Transfer, withdraw, deposit, journal cash or securities
 *   • Exercise options, submit multi-leg trades, or any other account mutation
 *
 * Every outbound broker HTTP call must go through `brokerFetch` in
 * `broker-http.ts`, which enforces this policy. CI scans the tree for
 * forbidden symbols and bare `fetch` to trader hosts.
 */

export const BROKER_CONNECTOR_MODE = "read_only_analysis" as const;

export type BrokerRequestPurpose =
  /** Authorization-code / refresh / client-credentials token endpoints. */
  | "oauth_token"
  /** OAuth discovery / protected-resource metadata (GET). */
  | "oauth_discovery"
  /** Dynamic client registration (POST) — registers a public OAuth client, not a trade. */
  | "oauth_registration"
  /** Account numbers, balances, positions, read-only market data for analysis. */
  | "portfolio_read";

/** Human-facing product promise (UI, legal, API). */
export const BROKER_READ_ONLY_PROMISE =
  "Broker connections are read-only. We import balances and holdings for analysis only — this app never places orders, never previews trades, and never moves money.";

/**
 * Operation names that must never appear as callable entry points in app code.
 * Used by static CI + runtime denylist for MCP tool names.
 */
export const FORBIDDEN_BROKER_OPERATIONS = [
  "place_order",
  "placeorder",
  "submit_order",
  "submitorder",
  "create_order",
  "createorder",
  "preview_order",
  "previeworder",
  "cancel_order",
  "cancelorder",
  "replace_order",
  "replaceorder",
  "modify_order",
  "execute_trade",
  "executetrade",
  "enter_order",
  "close_position",
  "closeposition",
  "liquidate",
  "transfer_cash",
  "transfer_securities",
  "withdraw",
  "deposit_funds",
  "journal_cash",
  "exercise_option",
  "exerciseoption",
  "place_equity_order",
  "place_option_order",
  "place_multileg_order",
  "place_oco_order",
  "place_previewed_order",
  "place_previewed",
] as const;

export type ForbiddenBrokerOperation =
  (typeof FORBIDDEN_BROKER_OPERATIONS)[number];

/** Path fragments that must never be requested on broker hosts. */
export const FORBIDDEN_BROKER_PATH_PATTERNS: readonly RegExp[] = [
  /\/orders?(?:\/|$|\?)/i,
  /\/trades?(?:\/|$|\?)/i,
  /\/transactions\/(?:submit|create)/i,
  /\/transfer/i,
  /\/withdraw/i,
  /\/deposit/i,
  /\/journal/i,
  /\/exercise/i,
  /\/liquidation/i,
  /\/preview.*order/i,
  /\/place[_-]?order/i,
  /\/submit[_-]?order/i,
  /\/cancel[_-]?order/i,
  /\/replace[_-]?order/i,
];

/** Host suffixes treated as broker / trading API surfaces. */
export const BROKER_API_HOST_SUFFIXES = [
  "schwabapi.com",
  "schwab.com",
  "api.schwabapi.com",
  "robinhood.com",
  "api.robinhood.com",
  "agent.robinhood.com",
  "ibkr.com",
  "interactivebrokers.com",
  "fidelity.com",
] as const;

export class BrokerWriteForbiddenError extends Error {
  readonly code = "BROKER_WRITE_FORBIDDEN" as const;
  readonly operation: string;

  constructor(operation: string, detail?: string) {
    super(
      detail ??
        `Broker write blocked (${operation}). ${BROKER_READ_ONLY_PROMISE}`,
    );
    this.name = "BrokerWriteForbiddenError";
    this.operation = operation;
  }
}

export function isBrokerApiHost(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return BROKER_API_HOST_SUFFIXES.some(
    (suffix) => host === suffix || host.endsWith(`.${suffix}`),
  );
}

export function pathLooksLikeBrokerWrite(pathname: string): boolean {
  const path = pathname || "/";
  return FORBIDDEN_BROKER_PATH_PATTERNS.some((re) => re.test(path));
}

export function isForbiddenBrokerOperationName(name: string): boolean {
  const n = name.toLowerCase().replace(/[^a-z0-9]/g, "");
  return FORBIDDEN_BROKER_OPERATIONS.some((op) => {
    const compact = op.replace(/[^a-z0-9]/g, "");
    return n === compact || n.includes(compact);
  });
}

/**
 * Runtime gate for MCP tool names (and any future tool router).
 * Throws if the tool is a write/trade operation.
 */
export function assertMcpToolReadOnly(toolName: string): void {
  if (isForbiddenBrokerOperationName(toolName)) {
    throw new BrokerWriteForbiddenError(
      toolName,
      `MCP tool "${toolName}" is a write/trade operation and is forbidden. ${BROKER_READ_ONLY_PROMISE}`,
    );
  }
  // Extra heuristics for common trading verbs in tool names
  if (
    /\b(place|submit|cancel|replace|execute|liquidate|withdraw|deposit)\b/i.test(
      toolName,
    ) &&
    /\b(order|trade|position|funds?|cash|transfer)\b/i.test(toolName)
  ) {
    throw new BrokerWriteForbiddenError(toolName);
  }
}

/**
 * Central authorization for any outbound broker HTTP request.
 * Call before every network call to a broker host.
 */
export function assertBrokerRequestAllowed(args: {
  url: string;
  method: string;
  purpose: BrokerRequestPurpose;
}): void {
  let parsed: URL;
  try {
    parsed = new URL(args.url);
  } catch {
    throw new BrokerWriteForbiddenError(
      "invalid_url",
      `Invalid broker URL (not parseable). ${BROKER_READ_ONLY_PROMISE}`,
    );
  }

  const method = (args.method || "GET").toUpperCase();
  const path = parsed.pathname + (parsed.search || "");

  if (pathLooksLikeBrokerWrite(path)) {
    throw new BrokerWriteForbiddenError(
      path,
      `Broker path denied (${path}). ${BROKER_READ_ONLY_PROMISE}`,
    );
  }

  switch (args.purpose) {
    case "portfolio_read": {
      if (method !== "GET" && method !== "HEAD") {
        throw new BrokerWriteForbiddenError(
          method,
          `Portfolio reads must use GET/HEAD, not ${method}. ${BROKER_READ_ONLY_PROMISE}`,
        );
      }
      return;
    }
    case "oauth_discovery": {
      if (method !== "GET" && method !== "HEAD") {
        throw new BrokerWriteForbiddenError(
          method,
          `OAuth discovery must use GET/HEAD, not ${method}.`,
        );
      }
      return;
    }
    case "oauth_token": {
      if (method !== "POST") {
        throw new BrokerWriteForbiddenError(
          method,
          `OAuth token endpoints must use POST (got ${method}).`,
        );
      }
      // Token URLs must look like token endpoints, never order paths
      if (
        !/oauth|token|authorize/i.test(path) &&
        !/\/v1\/oauth\/token/i.test(path)
      ) {
        throw new BrokerWriteForbiddenError(
          path,
          `POST denied for non-token broker path (${path}).`,
        );
      }
      return;
    }
    case "oauth_registration": {
      if (method !== "POST") {
        throw new BrokerWriteForbiddenError(method);
      }
      if (!/register|registration/i.test(path)) {
        throw new BrokerWriteForbiddenError(
          path,
          `POST denied for non-registration broker path (${path}).`,
        );
      }
      return;
    }
    default: {
      const _exhaustive: never = args.purpose;
      throw new BrokerWriteForbiddenError(String(_exhaustive));
    }
  }
}

/**
 * Fail closed if any code path tries to enable trading features.
 */
export function assertBrokerConnectorsReadOnly(): void {
  if (BROKER_CONNECTOR_MODE !== "read_only_analysis") {
    throw new BrokerWriteForbiddenError(
      BROKER_CONNECTOR_MODE,
      "Broker connector mode is not read_only_analysis.",
    );
  }
}
