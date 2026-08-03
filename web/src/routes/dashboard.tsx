import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Beaker,
  Link2,
  Loader2,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { NlvChart } from "@/components/dashboard/nlv-chart";
import { PositionsTable } from "@/components/dashboard/positions-table";
import { StatCard } from "@/components/dashboard/stat-card";
import { RedirectToSignIn } from "@/lib/auth/gates";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import {
  getAccountPortfolioFn,
  getDashboard,
} from "@/lib/portfolio/queries";
import { seedSimulatedSchwabFn } from "@/lib/portfolio/connector-queries";
import {
  positionsLookLikeDemo,
  visibleDashboardAccounts,
} from "@/lib/portfolio/dashboard-selection";
import { sumKnownNlvs } from "@/lib/portfolio/finance-math";
import type {
  AccountSummary,
  DashboardDataMode,
  DashboardPayload,
  FundSeriesPoint,
  PositionRow,
} from "@/lib/portfolio/types";
import { formatPct, formatUsd } from "@/lib/utils";

export const Route = createFileRoute("/dashboard")({
  component: DashboardPage,
});

function modeBadge(mode: DashboardDataMode): string {
  if (mode === "live") return "Live brokers";
  if (mode === "simulated") return "Simulated Schwab";
  return "Sample portfolio";
}

function accountLabel(a: AccountSummary): string {
  const mask = a.accountMask ? ` ${a.accountMask}` : "";
  return `${a.displayName}${mask}`;
}

function DashboardPage() {
  const { user, isPending } = useCurrentUserState();
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(
    null,
  );
  const [loadedAccountId, setLoadedAccountId] = useState<string | null>(null);
  const [series, setSeries] = useState<FundSeriesPoint[]>([]);
  const [positions, setPositions] = useState<PositionRow[]>([]);
  const [periodReturnPct, setPeriodReturnPct] = useState<number | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);

  function applyPayload(payload: DashboardPayload) {
    setData(payload);
    const initial =
      payload.selectedAccountId ??
      payload.accounts.find((a) => !a.isDemo && !a.isSimulated)?.id ??
      payload.accounts.find((a) => !a.isDemo)?.id ??
      payload.accounts[0]?.id ??
      null;
    setSelectedAccountId(initial);
    setLoadedAccountId(initial);
    setSeries(payload.series);
    setPositions(payload.positions);
    setPeriodReturnPct(payload.workspace.twrrPeriodReturnPct);
  }

  useEffect(() => {
    if (isPending) return;
    if (!user) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    getDashboard()
      .then((payload) => {
        if (cancelled) return;
        applyPayload(payload);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "Failed to load";
        if (msg === "Unauthorized") setError("unauthorized");
        else setError(msg);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user, isPending]);

  useEffect(() => {
    if (!user || !selectedAccountId) return;
    if (selectedAccountId === loadedAccountId) return;
    let cancelled = false;
    setDetailLoading(true);
    getAccountPortfolioFn({ data: { accountId: selectedAccountId } })
      .then((p) => {
        if (cancelled) return;
        setSeries(p.series);
        setPositions(p.positions);
        setPeriodReturnPct(p.periodReturnPct);
        setLoadedAccountId(p.accountId);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load account");
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user, selectedAccountId, loadedAccountId]);

  const selected = useMemo(() => {
    if (!data) return null;
    return (
      data.accounts.find((a) => a.id === selectedAccountId) ??
      data.accounts.find((a) => !a.isDemo && !a.isSimulated) ??
      data.accounts.find((a) => !a.isDemo) ??
      data.accounts[0] ??
      null
    );
  }, [data, selectedAccountId]);

  const dataMode: DashboardDataMode = data?.dataMode ?? "sample";
  const isLive = dataMode === "live";
  const isSimulated = dataMode === "simulated";
  const isSample = dataMode === "sample";

  const liveAccounts = useMemo(
    () => data?.accounts.filter((a) => !a.isDemo && !a.isSimulated) ?? [],
    [data],
  );
  const simAccounts = useMemo(
    () => data?.accounts.filter((a) => !a.isDemo && a.isSimulated) ?? [],
    [data],
  );
  const valueAccounts = isLive
    ? liveAccounts
    : isSimulated
      ? simAccounts
      : [];
  const totalValueAgg = sumKnownNlvs(valueAccounts.map((a) => a.latestNlv));
  const totalValueNlv = totalValueAgg.total ?? 0;
  const totalValueComplete = totalValueAgg.complete;

  const visibleAccounts = useMemo(
    () => (data ? visibleDashboardAccounts(data.accounts) : []),
    [data],
  );

  const selectedSharePct = useMemo(() => {
    if (
      !selected?.latestNlv ||
      !(totalValueNlv > 0) ||
      isSample ||
      !totalValueComplete
    ) {
      return null;
    }
    return (selected.latestNlv / totalValueNlv) * 100;
  }, [selected, totalValueNlv, isSample, totalValueComplete]);

  const posSymbols = positions.map((p) => p.symbol);
  const showingDemoHoldings = isLive && positionsLookLikeDemo(posSymbols);

  async function loadSimulated() {
    setSeeding(true);
    setError(null);
    try {
      await seedSimulatedSchwabFn();
      const payload = await getDashboard();
      applyPayload(payload);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load simulation");
    } finally {
      setSeeding(false);
    }
  }

  if (isPending) {
    return (
      <AppShell>
        <main className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
          <div className="h-8 w-48 animate-pulse rounded bg-bg-subtle" />
        </main>
      </AppShell>
    );
  }

  if (!user || error === "unauthorized") {
    return <RedirectToSignIn />;
  }

  const tone =
    periodReturnPct == null
      ? "default"
      : periodReturnPct >= 0
        ? "up"
        : "down";

  const selectedTitle = selected ? accountLabel(selected) : "No account selected";

  return (
    <AppShell>
      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
              Portfolio
            </p>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
              {data?.workspace.name ?? "Your workspace"}
            </h1>
            <p className="mt-1 text-sm text-fg-muted">
              {data
                ? isLive
                  ? `${liveAccounts.length} linked account${liveAccounts.length === 1 ? "" : "s"}`
                  : isSimulated
                    ? `${simAccounts.length} simulated account${simAccounts.length === 1 ? "" : "s"}`
                    : `${data.workspace.accountCount} account · sample data`
                : "Setting up your workspace…"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {isSample ? (
              <span className="inline-flex items-center gap-1.5 self-start rounded-full border border-border bg-bg-subtle px-3 py-1 text-xs font-medium text-fg-muted">
                <Beaker className="h-3.5 w-3.5" aria-hidden />
                Sample portfolio
              </span>
            ) : null}
            {isLive || isSimulated ? (
              <span
                className={
                  isLive
                    ? "inline-flex items-center gap-1.5 self-start rounded-full border border-success/40 bg-success/10 px-3 py-1 text-xs font-medium text-success"
                    : "inline-flex items-center gap-1.5 self-start rounded-full border border-border bg-bg-subtle px-3 py-1 text-xs font-medium text-fg-muted"
                }
              >
                {modeBadge(dataMode)}
              </span>
            ) : null}
            <Link
              to="/connectors"
              className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-bg-elevated px-3 text-xs font-medium text-fg transition-colors hover:bg-bg-subtle"
            >
              <Link2 className="h-3.5 w-3.5" aria-hidden />
              {isLive ? "Manage brokers" : "Connect brokers"}
            </Link>
          </div>
        </div>

        {error && error !== "unauthorized" ? (
          <div className="mt-6 flex items-start gap-2 rounded-[var(--radius-md)] border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}

        {data?.dataHealth?.showStaleBanner && data.dataHealth.message ? (
          <div className="mt-6 flex flex-col gap-2 rounded-[var(--radius-md)] border border-warning/35 bg-warning/10 px-4 py-3 text-sm text-fg sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
              <span>{data.dataHealth.message}</span>
            </div>
            {data.dataHealth.cta === "reconnect" || data.dataHealth.cta === "retry_sync" || data.dataHealth.cta === "connect" ? (
              <Link
                to="/connectors"
                className="inline-flex h-8 shrink-0 items-center rounded-[var(--radius-sm)] border border-border bg-bg-elevated px-3 text-xs font-medium text-fg"
              >
                {data.dataHealth.cta === "reconnect"
                  ? "Reconnect broker"
                  : data.dataHealth.cta === "connect"
                    ? "Connect broker"
                    : "Retry sync"}
              </Link>
            ) : null}
          </div>
        ) : null}

        {!data?.workspace.latestNlvComplete && isLive ? (
          <div className="mt-4 rounded-[var(--radius-md)] border border-border bg-bg-subtle px-4 py-2 text-xs text-fg-muted">
            Portfolio total is partial — some accounts have no known liquidation value. Missing balances are not treated as zero.
          </div>
        ) : null}

        {isSample ? (
          <div className="mt-6 rounded-[var(--radius-lg)] border border-border bg-bg-elevated px-4 py-4 text-sm text-fg-muted sm:px-5">
            <p>
              You’re viewing a <strong className="text-fg">sample</strong>{" "}
              portfolio (VOO / AAPL style holdings). Connect a broker or load
              simulated Schwab data to replace it.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={seeding}
                onClick={() => void loadSimulated()}
                className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-sm)] bg-primary px-3 text-xs font-medium text-primary-fg"
              >
                {seeding ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Beaker className="h-3.5 w-3.5" />
                )}
                Load simulated Schwab
              </button>
              <Link
                to="/connectors"
                className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-xs font-medium text-fg"
              >
                <Link2 className="h-3.5 w-3.5" />
                Connect real broker
              </Link>
            </div>
          </div>
        ) : null}

        {isSimulated ? (
          <div className="mt-6 rounded-[var(--radius-lg)] border border-border bg-bg-elevated px-4 py-3 text-sm text-fg-muted">
            Dashboard is on{" "}
            <strong className="text-fg">simulated Schwab</strong> import (not a
            live OAuth link). Sample chips are hidden.{" "}
            <Link
              to="/connectors"
              className="font-medium text-fg underline-offset-4 hover:underline"
            >
              Connect live broker or clear simulation
            </Link>
          </div>
        ) : null}

        {isLive ? (
          <div className="mt-6 rounded-[var(--radius-lg)] border border-success/25 bg-success/5 px-4 py-3 text-sm text-fg-muted">
            Showing <strong className="text-fg">live broker</strong> balances and
            holdings. Sample and simulated data are not used in totals.{" "}
            <Link
              to="/connectors"
              className="font-medium text-fg underline-offset-4 hover:underline"
            >
              Manage on Brokers
            </Link>
          </div>
        ) : null}

        {showingDemoHoldings ? (
          <div className="mt-4 flex items-start gap-2 rounded-[var(--radius-md)] border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Positions still look like sample holdings while live accounts
              exist — try another account chip or re-sync.
            </span>
          </div>
        ) : null}

        {/* Workspace total — sum across accounts, always distinct from selection */}
        {!isSample && valueAccounts.length > 0 ? (
          <section className="mt-8 rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-4 sm:p-6">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.12em] text-fg-subtle">
                  Workspace total
                </p>
                <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">
                  {loading && !data ? "…" : formatUsd(totalValueNlv)}
                </p>
                <p className="mt-1 text-sm text-fg-muted">
                  Sum of {valueAccounts.length} account
                  {valueAccounts.length === 1 ? "" : "s"}
                  {isLive ? " (live broker data)" : " (simulated)"}
                </p>
              </div>
            </div>
            <ul className="mt-5 divide-y divide-border border-t border-border">
              {valueAccounts.map((a) => {
                const active = a.id === selected?.id;
                const share =
                  a.latestNlv != null && totalValueNlv > 0
                    ? (a.latestNlv / totalValueNlv) * 100
                    : null;
                return (
                  <li key={a.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedAccountId(a.id)}
                      className={
                        active
                          ? "flex w-full items-center justify-between gap-3 bg-bg-subtle/80 px-1 py-3 text-left sm:px-2"
                          : "flex w-full items-center justify-between gap-3 px-1 py-3 text-left transition-colors hover:bg-bg-subtle/50 sm:px-2"
                      }
                    >
                      <div className="min-w-0">
                        <p
                          className={
                            active
                              ? "truncate text-sm font-semibold text-fg"
                              : "truncate text-sm font-medium text-fg"
                          }
                        >
                          {accountLabel(a)}
                          {active ? (
                            <span className="ml-2 text-xs font-medium text-primary">
                              viewing
                            </span>
                          ) : null}
                        </p>
                        <p className="mt-0.5 text-xs text-fg-subtle">
                          {a.broker}
                          {share != null
                            ? ` · ${share.toFixed(1)}% of total`
                            : ""}
                        </p>
                      </div>
                      <p className="shrink-0 text-sm font-semibold tabular-nums text-fg">
                        {formatUsd(a.latestNlv)}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null}

        <div className="mt-6 grid gap-3 sm:grid-cols-3">
          <StatCard
            label={isSample ? "Net liquidation" : "Workspace total"}
            value={
              loading && !data
                ? "…"
                : formatUsd(
                    isSample ? (selected?.latestNlv ?? null) : totalValueNlv,
                  )
            }
            hint={
              isSample
                ? selected?.latestAsOf
                  ? `As of ${selected.latestAsOf}`
                  : "Sample fund"
                : `${valueAccounts.length} account${valueAccounts.length === 1 ? "" : "s"} combined`
            }
          />
          <StatCard
            label="This account"
            value={
              loading && !data ? "…" : formatUsd(selected?.latestNlv ?? null)
            }
            hint={
              selected
                ? `${accountLabel(selected)}${
                    selectedSharePct != null
                      ? ` · ${selectedSharePct.toFixed(0)}% of total`
                      : ""
                  }`
                : "Select an account below"
            }
          />
          <StatCard
            label="Period return"
            value={
              loading || detailLoading ? "…" : formatPct(periodReturnPct)
            }
            tone={tone as "default" | "up" | "down"}
            hint={
              series.length < 2
                ? `For ${selectedTitle} — need ≥2 daily points`
                : `For ${selectedTitle}`
            }
          />
        </div>

        {/* Account picker — chips show NLV so selection is obvious */}
        {visibleAccounts.length > 0 ? (
          <section className="mt-8">
            <div className="mb-3 flex items-baseline justify-between gap-2">
              <h2 className="text-sm font-semibold text-fg">Accounts</h2>
              <p className="text-xs text-fg-muted">
                Chart and positions below are for the selected account only
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              {visibleAccounts.map((a) => {
                const active = a.id === selected?.id;
                return (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => setSelectedAccountId(a.id)}
                    className={
                      active
                        ? "flex min-w-[min(100%,14rem)] flex-col items-start rounded-[var(--radius-md)] border border-fg/35 bg-bg-subtle px-3 py-2.5 text-left"
                        : "flex min-w-[min(100%,14rem)] flex-col items-start rounded-[var(--radius-md)] border border-border bg-bg px-3 py-2.5 text-left transition-colors hover:bg-bg-subtle"
                    }
                  >
                    <span
                      className={
                        active
                          ? "text-xs font-semibold text-fg"
                          : "text-xs font-medium text-fg-muted"
                      }
                    >
                      {accountLabel(a)}
                    </span>
                    <span className="mt-1 text-sm font-semibold tabular-nums text-fg">
                      {formatUsd(a.latestNlv)}
                    </span>
                    <span className="mt-0.5 text-[11px] text-fg-subtle">
                      {a.broker}
                      {active ? " · selected" : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        ) : null}

        {/* Sticky-feel context bar for detail sections */}
        {selected ? (
          <div className="mt-8 rounded-[var(--radius-md)] border border-primary/25 bg-primary/5 px-4 py-3">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-fg-subtle">
              Viewing account
            </p>
            <p className="mt-0.5 text-sm font-semibold text-fg">
              {selectedTitle}
              <span className="ml-2 font-normal text-fg-muted">
                · {formatUsd(selected.latestNlv)}
                {selected.latestAsOf ? ` · as of ${selected.latestAsOf}` : ""}
              </span>
            </p>
            <p className="mt-1 text-xs text-fg-muted">
              Chart and positions below apply only to this account — not the
              workspace total.
            </p>
          </div>
        ) : null}

        <section className="mt-4 rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-4 sm:p-6">
          <div className="mb-4 flex items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">Account value over time</h2>
              <p className="text-xs text-fg-muted">
                {selectedTitle}
                {selected?.isDemo ? " · sample" : ""}
                {selected?.isSimulated ? " · simulated" : ""}
              </p>
            </div>
            {detailLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-fg-muted" />
            ) : null}
          </div>
          {series.length === 0 && !detailLoading ? (
            <p className="py-10 text-center text-sm text-fg-muted">
              No value history yet for {selectedTitle}. Run{" "}
              <Link
                to="/connectors"
                className="font-medium text-fg underline-offset-4 hover:underline"
              >
                Sync
              </Link>{" "}
              on Brokers to pull the latest balances.
            </p>
          ) : (
            <NlvChart series={series} />
          )}
        </section>

        <section className="mt-6 rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-4 sm:p-6">
          <div className="mb-4 flex items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">Positions</h2>
              <p className="text-xs text-fg-muted">{selectedTitle}</p>
            </div>
            {detailLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-fg-muted" />
            ) : (
              <span className="text-xs text-fg-subtle">
                {positions.length} holding{positions.length === 1 ? "" : "s"}
              </span>
            )}
          </div>
          {positions.length === 0 && !detailLoading ? (
            <p className="py-6 text-center text-sm text-fg-muted">
              No positions stored for {selectedTitle} yet.
            </p>
          ) : (
            <PositionsTable positions={positions} />
          )}
        </section>

        <p className="mt-8 text-xs text-fg-subtle">
          Prefer an AI assistant? Create an API key in{" "}
          <Link
            to="/settings"
            className="text-fg-muted underline-offset-4 hover:underline"
          >
            Settings
          </Link>{" "}
          so agents can read the same numbers you see here.
        </p>
      </main>
    </AppShell>
  );
}
