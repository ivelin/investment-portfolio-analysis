/**
 * Sole outbound HTTP entry for broker / trading API hosts.
 *
 * All Schwab, Robinhood, IBKR (and future) broker network I/O must use
 * `brokerFetch`. Bare `fetch()` to those hosts is forbidden by CI scan.
 */
import {
  assertBrokerRequestAllowed,
  assertBrokerConnectorsReadOnly,
  isBrokerApiHost,
  type BrokerRequestPurpose,
  BrokerWriteForbiddenError,
} from "./read-only-policy";

export type BrokerFetchInit = RequestInit & {
  purpose: BrokerRequestPurpose;
  /** Optional timeout ms (default 20s). */
  timeoutMs?: number;
};

/**
 * Policy-enforced fetch for broker APIs.
 * - Always asserts global read-only mode
 * - Validates method/path/purpose before any network I/O
 * - Refuses non-broker hosts when used intentionally for broker traffic
 */
export async function brokerFetch(
  input: string | URL,
  init: BrokerFetchInit,
): Promise<Response> {
  assertBrokerConnectorsReadOnly();

  const url = typeof input === "string" ? input : input.toString();
  const method = (init.method || "GET").toUpperCase();

  assertBrokerRequestAllowed({
    url,
    method,
    purpose: init.purpose,
  });

  let hostname = "";
  try {
    hostname = new URL(url).hostname;
  } catch {
    throw new BrokerWriteForbiddenError("invalid_url");
  }

  // portfolio_read must hit a known broker host; oauth may hit auth hosts we list
  if (init.purpose === "portfolio_read" && !isBrokerApiHost(hostname)) {
    throw new BrokerWriteForbiddenError(
      hostname,
      `portfolio_read refused for non-broker host ${hostname}`,
    );
  }

  const { purpose: _p, timeoutMs, ...rest } = init;
  const signal =
    rest.signal ??
    AbortSignal.timeout(
      typeof timeoutMs === "number" && timeoutMs > 0 ? timeoutMs : 20_000,
    );

  return fetch(url, {
    ...rest,
    method,
    signal,
  });
}

/** Test helper: assert a would-be request is legal without network. */
export function assertBrokerFetchWouldAllow(
  url: string,
  init: Pick<BrokerFetchInit, "method" | "purpose">,
): void {
  assertBrokerConnectorsReadOnly();
  assertBrokerRequestAllowed({
    url,
    method: init.method || "GET",
    purpose: init.purpose,
  });
}
