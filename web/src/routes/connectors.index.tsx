import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Beaker,
  CheckCircle2,
  Link2,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Unplug,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { RedirectToSignIn } from "@/lib/auth/gates";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import {
  clearSimulatedSchwabFn,
  connectBrokerFn,
  disconnectBrokerFn,
  getConnectors,
  seedSimulatedSchwabFn,
  syncBrokersFn,
  type ConnectorStatus,
} from "@/lib/portfolio/connector-queries";
import { navigateToBrokerOAuth } from "@/lib/portfolio/oauth-navigate";
import type { BrokerId } from "@/lib/portfolio/brokers/catalog";
import { BROKER_READ_ONLY_PROMISE } from "@/lib/portfolio/brokers/read-only-policy";
import {
  classifyConnectorUiStatus,
  connectorUiLabel,
  isLinkedStatus,
  primaryConnectCta,
} from "@/lib/portfolio/connector-status";
import { formatUsd } from "@/lib/utils";

export const Route = createFileRoute("/connectors/")({
  component: ConnectorsPage,
});

function friendlyOAuthError(reason: string | null): string {
  switch (reason) {
    case "sign_in_required":
      return "Please stay signed in while you finish connecting at the broker, then try again.";
    case "session_mismatch":
      return "That connection was started by a different sign-in. Start Connect again from this account.";
    case "expired_state":
      return "That connection link expired. Start Connect again.";
    case "token_exchange":
      return "We couldn’t finish linking with the broker. Try again in a moment.";
    default:
      return "We couldn’t finish connecting that broker. Nothing was saved — try again.";
  }
}

function labelBroker(b: string): string {
  const map: Record<string, string> = {
    schwab: "Charles Schwab",
    robinhood: "Robinhood",
    ibkr: "Interactive Brokers",
    fidelity: "Fidelity",
  };
  return map[b] || b;
}

function ConnectorsPage() {
  const { user, isPending } = useCurrentUserState();
  const [items, setItems] = useState<ConnectorStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const list = await getConnectors();
    setItems(list);
  }, []);

  useEffect(() => {
    if (isPending || !user) return;
    let cancelled = false;
    setError(null);
    const params = new URLSearchParams(window.location.search);
    const oauth = params.get("oauth");
    if (oauth === "success") {
      const b = params.get("broker") ?? "your broker";
      setNotice(
        `${labelBroker(b)} is connected (read-only). Balances stay private to this workspace.`,
      );
      window.history.replaceState({}, "", "/connectors");
    } else if (oauth === "error") {
      setError(friendlyOAuthError(params.get("reason")));
      window.history.replaceState({}, "", "/connectors");
    }
    reload().catch((err: unknown) => {
      if (cancelled) return;
      const msg = err instanceof Error ? err.message : "Failed to load";
      if (msg === "Unauthorized") setError("unauthorized");
      else setError(msg);
    });
    return () => {
      cancelled = true;
    };
  }, [user, isPending, reload]);

  if (isPending) {
    return (
      <AppShell>
        <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
          <div className="h-8 w-56 animate-pulse rounded bg-bg-subtle" />
        </main>
      </AppShell>
    );
  }

  if (!user || error === "unauthorized") {
    return <RedirectToSignIn />;
  }

  async function run(
    key: string,
    fn: () => Promise<unknown>,
    okMsg: string | ((result: unknown) => string),
  ) {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      const result = await fn();
      await reload();
      setNotice(typeof okMsg === "function" ? okMsg(result) : okMsg);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Action failed");
      await reload().catch(() => undefined);
    } finally {
      setBusy(null);
    }
  }

  async function onConnect(broker: BrokerId) {
    setBusy(`connect-${broker}`);
    setError(null);
    setNotice(null);
    try {
      const result = await connectBrokerFn({
        data: { broker, origin: window.location.origin },
      });
      if (result.kind === "oauth_redirect") {
        navigateToBrokerOAuth(result.authorizeUrl);
        return;
      }
      window.location.href = `/connectors/setup/${broker}`;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Connect failed");
    } finally {
      setBusy(null);
    }
  }

  const schwab = items.find((c) => c.broker === "schwab");
  const hasSim = Boolean(schwab?.isSimulated);
  const hasRealSchwab = Boolean(
    schwab && isLinkedStatus(schwab.status) && !schwab.isSimulated,
  );

  return (
    <AppShell>
      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
          Brokers
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Connect accounts
        </h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-fg-muted">
          Link brokers for{" "}
          <strong className="font-medium text-fg">read-only</strong> analysis
          (balances and holdings). Open this preview in its own browser tab
          before approving access.{" "}
          <strong className="font-medium text-fg">Sync</strong> re-imports
          positions — it never places orders.
        </p>

        <div className="mt-4 flex items-start gap-2 rounded-[var(--radius-lg)] border border-border bg-bg-elevated px-4 py-3 text-xs leading-relaxed text-fg-muted">
          <ShieldCheck
            className="mt-0.5 h-4 w-4 shrink-0 text-success"
            aria-hidden
          />
          <span>{BROKER_READ_ONLY_PROMISE}</span>
        </div>

        {!hasRealSchwab ? (
          <div className="mt-6 rounded-[var(--radius-lg)] border border-border bg-bg-elevated px-4 py-4">
            <div className="flex items-start gap-2">
              <Beaker className="mt-0.5 h-4 w-4 shrink-0 text-fg-muted" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-fg">
                  Simulated Schwab import
                </p>
                <p className="mt-1 text-xs leading-relaxed text-fg-muted">
                  Load multi-account sample Schwab holdings (SGOV, TSLA,
                  IBIT…) so the dashboard switches off the demo fund. Not real
                  money — safe for preview. Clear anytime.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy != null}
                    onClick={() =>
                      void run(
                        "seed-sim",
                        () => seedSimulatedSchwabFn(),
                        (r) => {
                          const x = r as {
                            accountCount?: number;
                            totalNlv?: number;
                          };
                          return `Simulated Schwab loaded: ${x.accountCount ?? 3} accounts · ${formatUsd(x.totalNlv ?? null)}. Open Dashboard.`;
                        },
                      )
                    }
                    className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-sm)] bg-primary px-3 text-xs font-medium text-primary-fg"
                  >
                    {busy === "seed-sim" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Beaker className="h-3.5 w-3.5" />
                    )}
                    {hasSim ? "Reload simulated Schwab" : "Load simulated Schwab"}
                  </button>
                  {hasSim ? (
                    <button
                      type="button"
                      disabled={busy != null}
                      onClick={() =>
                        void run(
                          "clear-sim",
                          () => clearSimulatedSchwabFn(),
                          "Simulation cleared — sample fund is primary again.",
                        )
                      }
                      className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-xs font-medium text-fg"
                    >
                      Clear simulation
                    </button>
                  ) : null}
                  <Link
                    to="/dashboard"
                    className="inline-flex h-10 items-center rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-xs font-medium text-fg-muted hover:text-fg"
                  >
                    Open dashboard
                  </Link>
                </div>
              </div>
            </div>
          </div>
        ) : null}

        {notice ? (
          <div className="mt-6 flex items-start gap-2 rounded-[var(--radius-lg)] border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{notice}</span>
          </div>
        ) : null}
        {error && error !== "unauthorized" ? (
          <div className="mt-6 flex items-start gap-2 rounded-[var(--radius-lg)] border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="mt-8 space-y-3">
          {items.map((c) => {
            const ui = classifyConnectorUiStatus({
              status: c.status,
              oauthConfigured: c.oauthConfigured,
            });
            const cta = primaryConnectCta({
              status: c.status,
              oauthConfigured: c.oauthConfigured,
            });
            const linked = isLinkedStatus(c.status);
            const needsReauth = c.status === "error" && !c.isSimulated;
            return (
              <div
                key={c.broker}
                className="flex flex-col gap-3 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-semibold text-fg">
                      {c.label}
                    </h2>
                    <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-fg-muted">
                      {c.isSimulated ? "Simulated" : connectorUiLabel(ui)}
                    </span>
                    <span className="rounded-full border border-success/30 bg-success/10 px-2 py-0.5 text-[11px] text-success">
                      Read-only
                    </span>
                    {c.accountCount > 0 ? (
                      <span className="text-[11px] text-fg-subtle">
                        {c.accountCount} account
                        {c.accountCount === 1 ? "" : "s"}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 text-sm text-fg-muted">{c.description}</p>
                  {c.lastError && !c.isSimulated ? (
                    <p className="mt-1 text-xs text-danger">
                      {c.lastError}
                      {!needsReauth
                        ? " — connection kept; retry Sync when ready."
                        : " — re-authorize to restore the live link."}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {linked ? (
                    <>
                      {!c.isSimulated ? (
                        <button
                          type="button"
                          disabled={busy != null}
                          onClick={() =>
                            void run(
                              `sync-${c.broker}`,
                              () =>
                                syncBrokersFn({ data: { broker: c.broker } }),
                              "Sync finished (read-only import).",
                            )
                          }
                          className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-xs font-medium text-fg"
                        >
                          {busy === `sync-${c.broker}` ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <RefreshCw className="h-3.5 w-3.5" />
                          )}
                          {needsReauth ? "Retry sync" : "Sync"}
                        </button>
                      ) : null}
                      {needsReauth ? (
                        <button
                          type="button"
                          disabled={busy != null}
                          onClick={() => void onConnect(c.broker)}
                          className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-sm)] bg-primary px-3 text-xs font-medium text-primary-fg"
                        >
                          {busy === `connect-${c.broker}` ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Link2 className="h-3.5 w-3.5" />
                          )}
                          Reconnect
                        </button>
                      ) : null}
                      <button
                        type="button"
                        disabled={busy != null}
                        onClick={() =>
                          void run(
                            `disc-${c.broker}`,
                            () =>
                              disconnectBrokerFn({
                                data: { broker: c.broker },
                              }),
                            c.isSimulated
                              ? "Simulation cleared."
                              : "Disconnected.",
                          )
                        }
                        className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-xs font-medium text-fg"
                      >
                        <Unplug className="h-3.5 w-3.5" />
                        {c.isSimulated ? "Clear sim" : "Disconnect"}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      disabled={busy != null}
                      onClick={() => void onConnect(c.broker)}
                      className="inline-flex h-10 items-center gap-1.5 rounded-[var(--radius-sm)] bg-primary px-3 text-xs font-medium text-primary-fg"
                    >
                      {busy === `connect-${c.broker}` ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Link2 className="h-3.5 w-3.5" />
                      )}
                      {cta === "how_to_connect" ? "Set up" : "Connect"}
                    </button>
                  )}
                  <Link
                    to="/connectors/setup/$broker"
                    params={{ broker: c.broker }}
                    className="inline-flex h-10 items-center rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-xs font-medium text-fg-muted hover:text-fg"
                  >
                    Details
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      </main>
    </AppShell>
  );
}
