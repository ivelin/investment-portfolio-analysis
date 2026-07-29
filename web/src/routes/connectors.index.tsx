import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Link2,
  Loader2,
  RefreshCw,
  Unplug,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { RedirectToSignIn } from "@/lib/auth/gates";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import {
  connectBrokerFn,
  disconnectBrokerFn,
  getConnectors,
  syncBrokersFn,
  type ConnectorStatus,
} from "@/lib/portfolio/connector-queries";
import type { BrokerId } from "@/lib/portfolio/brokers/catalog";
import {
  classifyConnectorUiStatus,
  connectorUiLabel,
  primaryConnectCta,
} from "@/lib/portfolio/connector-status";

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
        `${labelBroker(b)} is connected. Your balances stay private to this workspace.`,
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
    okMsg: string,
  ) {
    setBusy(key);
    setError(null);
    setNotice(null);
    try {
      await fn();
      await reload();
      setNotice(okMsg);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Action failed");
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
        window.location.href = result.authorizeUrl;
        return;
      }
      setError(result.message);
      await reload();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Connect failed");
    } finally {
      setBusy(null);
    }
  }

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
          Link a brokerage so this workspace can show your real balances and
          holdings. You approve access at the broker — we never ask for your
          brokerage password here.
        </p>

        {error && error !== "unauthorized" ? (
          <div className="mt-6 flex items-start gap-2 rounded-[var(--radius-md)] border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}
        {notice ? (
          <div className="mt-6 flex items-start gap-2 rounded-[var(--radius-md)] border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{notice}</span>
          </div>
        ) : null}

        <div className="mt-8 space-y-4">
          {items.map((c) => {
            const broker = c.broker as BrokerId;
            const cta = primaryConnectCta({
              status: c.status,
              oauthConfigured: c.oauthConfigured,
            });
            const ui = classifyConnectorUiStatus({
              status: c.status,
              oauthConfigured: c.oauthConfigured,
            });
            return (
              <article
                key={c.broker}
                className="rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-5 sm:p-6"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="text-base font-semibold text-fg">
                        {c.label}
                      </h2>
                      <StatusPill ui={ui} />
                    </div>
                    <p className="mt-1 text-sm text-fg-muted">{c.description}</p>
                    <p className="mt-1 text-xs text-fg-subtle">
                      {c.oauthConfigured
                        ? "Ready to connect"
                        : "Follow the short setup guide to finish linking"}
                      {c.accountCount > 0
                        ? ` · ${c.accountCount} account${c.accountCount === 1 ? "" : "s"} linked`
                        : ""}
                    </p>
                    {c.lastSyncAt ? (
                      <p className="mt-1 text-xs text-fg-subtle">
                        Last updated {new Date(c.lastSyncAt).toLocaleString()}
                      </p>
                    ) : null}
                    {c.lastError ? (
                      <p className="mt-1 text-xs text-danger">{c.lastError}</p>
                    ) : null}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {cta === "how_to_connect" ? (
                      <Link
                        to="/connectors/setup/$broker"
                        params={{ broker }}
                        className="inline-flex h-10 min-h-10 items-center gap-2 rounded-[var(--radius-sm)] bg-primary px-4 text-sm font-medium text-primary-fg transition-opacity hover:opacity-90"
                      >
                        <Link2 className="h-4 w-4" aria-hidden />
                        How to connect
                      </Link>
                    ) : null}
                    {cta === "connect" ? (
                      <>
                        <button
                          type="button"
                          disabled={busy != null}
                          onClick={() => void onConnect(broker)}
                          className="inline-flex h-10 min-h-10 items-center gap-2 rounded-[var(--radius-sm)] bg-primary px-4 text-sm font-medium text-primary-fg transition-opacity hover:opacity-90 disabled:opacity-40"
                        >
                          {busy === `connect-${c.broker}` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Link2 className="h-4 w-4" aria-hidden />
                          )}
                          Connect
                        </button>
                        <Link
                          to="/connectors/setup/$broker"
                          params={{ broker }}
                          className="inline-flex h-10 min-h-10 items-center rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-xs font-medium text-fg-muted hover:bg-bg-subtle"
                        >
                          Setup help
                        </Link>
                      </>
                    ) : null}
                    {cta === "refresh_disconnect" ? (
                      <>
                        <button
                          type="button"
                          disabled={busy != null}
                          onClick={() =>
                            void run(
                              `sync-${c.broker}`,
                              () =>
                                syncBrokersFn({
                                  data: { broker },
                                }),
                              `${c.label} updated`,
                            )
                          }
                          className="inline-flex h-10 min-h-10 items-center gap-2 rounded-[var(--radius-sm)] border border-border bg-bg px-4 text-sm font-medium text-fg transition-colors hover:bg-bg-subtle disabled:opacity-40"
                        >
                          {busy === `sync-${c.broker}` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <RefreshCw className="h-4 w-4" aria-hidden />
                          )}
                          Refresh
                        </button>
                        <button
                          type="button"
                          disabled={busy != null}
                          onClick={() =>
                            void run(
                              `disc-${c.broker}`,
                              () =>
                                disconnectBrokerFn({
                                  data: { broker },
                                }),
                              `${c.label} disconnected`,
                            )
                          }
                          className="inline-flex h-10 min-h-10 items-center gap-2 rounded-[var(--radius-sm)] border border-border bg-bg px-4 text-sm font-medium text-fg-muted transition-colors hover:bg-bg-subtle disabled:opacity-40"
                        >
                          {busy === `disc-${c.broker}` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Unplug className="h-4 w-4" aria-hidden />
                          )}
                          Disconnect
                        </button>
                      </>
                    ) : null}
                  </div>
                </div>
              </article>
            );
          })}
        </div>

        <div className="mt-8 rounded-[var(--radius-lg)] border border-border bg-bg p-5 text-sm leading-relaxed text-fg-muted">
          <p className="font-medium text-fg">What to expect</p>
          <ul className="mt-2 list-disc space-y-1.5 pl-5">
            <li>
              You’ll sign in with the broker and approve read access for this
              app.
            </li>
            <li>
              Linked accounts appear only in{" "}
              <strong className="font-medium text-fg">your</strong> workspace.
            </li>
            <li>You can disconnect anytime.</li>
            <li>
              Stay signed into this app while you finish at the broker so the
              connection can complete securely.
            </li>
          </ul>
          <p className="mt-4">
            <Link
              to="/dashboard"
              className="font-medium text-fg underline-offset-4 hover:underline"
            >
              Back to dashboard
            </Link>
          </p>
        </div>
      </main>
    </AppShell>
  );
}

function labelBroker(id: string): string {
  if (id === "schwab") return "Schwab";
  if (id === "robinhood") return "Robinhood";
  if (id === "ibkr") return "Interactive Brokers";
  return id;
}

function StatusPill({
  ui,
}: {
  ui: ReturnType<typeof classifyConnectorUiStatus>;
}) {
  const label = connectorUiLabel(ui);
  const className =
    ui === "connected"
      ? "rounded-full border border-success/40 bg-success/10 px-2 py-0.5 text-[11px] font-medium text-success"
      : ui === "needs_attention"
        ? "rounded-full border border-danger/40 bg-danger/10 px-2 py-0.5 text-[11px] font-medium text-danger"
        : "rounded-full border border-border bg-bg-subtle px-2 py-0.5 text-[11px] font-medium text-fg-muted";
  return <span className={className}>{label}</span>;
}
