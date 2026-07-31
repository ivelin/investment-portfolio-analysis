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
import type {
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
  const totalValueNlv = valueAccounts.reduce(
    (s, a) => s + (a.latestNlv ?? 0),
    0,
  );

  const visibleAccounts = useMemo(
    () => (data ? visibleDashboardAccounts(data.accounts) : []),
    [data],
  );

  const posSymbols = positions.map((p) => p.symbol);
  // Only warn about demo holdings when we claim to be on live data.
  const showingDemoHoldings =
    isLive && positionsLookLikeDemo(posSymbols);

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

        {/* Sample only: offer sim or real connect. Never show when live. */}
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

        {/* Simulated only — never when live broker data is primary */}
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

        {/* Live: quiet confirmation, no dummy/sim language */}
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

        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          <StatCard
            label={isSample ? "Net liquidation" : "Total value"}
            value={
              loading && !data
                ? "…"
                : formatUsd(
                    isSample
                      ? (selected?.latestNlv ?? null)
                      : totalValueNlv,
                  )
            }
            hint={
              isLive
                ? `${liveAccounts.length} linked account${liveAccounts.length === 1 ? "" : "s"}`
                : isSimulated
                  ? `${simAccounts.length} simulated account${simAccounts.length === 1 ? "" : "s"}`
                  : selected?.latestAsOf
                    ? `As of ${selected.latestAsOf}`
                    : "Awaiting series"
            }
          />
          <StatCard
            label="Selected account"
            value={
              loading && !data ? "…" : formatUsd(selected?.latestNlv ?? null)
            }
            hint={
              selected
                ? `${selected.displayName}${selected.accountMask ? ` ${selected.accountMask}` : ""}`
                : "Primary"
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
                ? "Need at least two daily points (sync over time)"
                : "From first to last available day on the selected account"
            }
          />
        </div>

        {visibleAccounts.length > 1 ? (
          <div className="mt-6 flex flex-wrap gap-2">
            {visibleAccounts.map((a) => {
              const active = a.id === selected?.id;
              return (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => setSelectedAccountId(a.id)}
                  className={
                    active
                      ? "rounded-full border border-fg/30 bg-bg-subtle px-3 py-1.5 text-xs font-medium text-fg"
                      : "rounded-full border border-border bg-bg px-3 py-1.5 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-subtle hover:text-fg"
                  }
                >
                  {a.displayName}
                  {a.accountMask ? ` ${a.accountMask}` : ""}
                  <span className="ml-1 text-fg-subtle">· {a.broker}</span>
                </button>
              );
            })}
          </div>
        ) : null}

        <section className="mt-8 rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-4 sm:p-6">
          <div className="mb-4 flex items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">Account value over time</h2>
              <p className="text-xs text-fg-muted">
                {selected?.displayName ?? "Primary account"}
                {selected?.accountMask ? ` · ${selected.accountMask}` : ""}
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
              No value history yet for this account. Run{" "}
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
            <h2 className="text-sm font-semibold">Positions</h2>
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
              No positions stored for this account yet.
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
