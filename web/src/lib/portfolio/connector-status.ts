export type ConnectorDbStatus =
  | "connected"
  | "disconnected"
  | "error"
  | "pending_oauth"
  | string;

export type ConnectorUiStatus =
  | "connected"
  | "needs_attention"
  | "finish_at_broker"
  | "setup_needed"
  | "not_connected";

export type ConnectCta =
  | "how_to_connect"
  | "connect"
  | "refresh_disconnect"
  | "retry_sync"
  | "reconnect"
  | "none";

/** Tokens are still stored; user should retry sync, not re-OAuth. */
export function isLinkedStatus(status: ConnectorDbStatus): boolean {
  return status === "connected" || status === "error";
}

export function classifyConnectorUiStatus(args: {
  status: ConnectorDbStatus;
  oauthConfigured: boolean;
}): ConnectorUiStatus {
  if (args.status === "connected") return "connected";
  if (args.status === "error") return "needs_attention";
  if (args.status === "pending_oauth") return "finish_at_broker";
  if (!args.oauthConfigured) return "setup_needed";
  return "not_connected";
}

export function primaryConnectCta(args: {
  status: ConnectorDbStatus;
  oauthConfigured: boolean;
}): ConnectCta {
  if (args.status === "connected") return "refresh_disconnect";
  if (args.status === "error") return "retry_sync";
  if (!args.oauthConfigured) return "how_to_connect";
  return "connect";
}

export function connectorUiLabel(status: ConnectorUiStatus): string {
  switch (status) {
    case "connected":
      return "Connected";
    case "needs_attention":
      return "Needs attention";
    case "finish_at_broker":
      return "Finish at broker";
    case "setup_needed":
      return "Setup needed";
    case "not_connected":
      return "Not connected";
    default:
      return "Unknown";
  }
}
