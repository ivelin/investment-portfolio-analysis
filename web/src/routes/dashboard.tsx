import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Beaker, Link2 } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { NlvChart } from "@/components/dashboard/nlv-chart";
import { PositionsTable } from "@/components/dashboard/positions-table";
import { StatCard } from "@/components/dashboard/stat-card";
import { RedirectToSignIn } from "@/lib/auth/gates";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import { getDashboard } from "@/lib/portfolio/queries";
import type { DashboardPayload } from "@/lib/portfolio/types";
import { formatPct, formatUsd } from "@/lib/utils";

export const Route = createFileRoute("/dashboard")({
  component: DashboardPage,
});

function DashboardPage() {
  const { user, isPending } = useCurrentUserState();
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(
    null,
  );

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
        setData(payload);
        const live = payload.accounts.find((a) => !a.isDemo);
        setSelectedAccountId(live?.id ?? payload.accounts[0]?.id ?? null);
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

  const selected = useMemo(() => {
    if (!data) return null;
    return (
      data.accounts.find((a) => a.id === selectedAccountId) ??
      data.accounts[0] ??
      null
    );
  }, [data, selectedAccountId]);

  const view = useMemo(() => {
    if (!data || !selected) return data;
    if (selected.id === data.accounts[0]?.id) return data;
    return {
      ...data,
      series: data.series,
      positions: data.positions,
      workspace: {
        ...data.workspace,
        latestNlv: selected.latestNlv,
        latestAsOf: selected.latestAsOf,
      },
    };
  }, [data, selected]);

  const liveAccounts = useMemo(
    () => data?.accounts.filter((a) => !a.isDemo) ?? [],
    [data],
  );
  const hasLive = liveAccounts.length > 0;
  const totalLiveNlv = liveAccounts.reduce(
    (s, a) => s + (a.latestNlv ?? 0),
    0,
  );

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

  const period = view?.workspace.twrrPeriodReturnPct ?? null;
  const tone =
    period == null ? "default" : period >= 0 ? "up" : "down";

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
                ? `${data.workspace.accountCount} account${data.workspace.accountCount === 1 ? "" : "s"}${
                    hasLive
                      ? ` · ${liveAccounts.length} linked`
                      : " · sample data"
                  }`
                : "Setting up your workspace…"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {data?.workspace.isDemo && !hasLive ? (
              <span className="inline-flex items-center gap-1.5 self-start rounded-full border border-border bg-bg-subtle px-3 py-1 text-xs font-medium text-fg-muted">
                <Beaker className="h-3.5 w-3.5" aria-hidden />
                Sample portfolio
              </span>
            ) : null}
            {hasLive ? (
              <span className="inline-flex items-center gap-1.5 self-start rounded-full border border-success/40 bg-success/10 px-3 py-1 text-xs font-medium text-success">
                Brokers linked
              </span>
            ) : null}
            <Link
              to="/connectors"
              className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-bg-elevated px-3 text-xs font-medium text-fg transition-colors hover:bg-bg-subtle"
            >
              <Link2 className="h-3.5 w-3.5" aria-hidden />
              Connect brokers
            </Link>
          </div>
        </div>

        {error && error !== "unauthorized" ? (
          <div className="mt-6 flex items-start gap-2 rounded-[var(--radius-md)] border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{error}</span>
          </div>
        ) : null}

        {!hasLive ? (
          <div className="mt-6 rounded-[var(--radius-lg)] border border-border bg-bg-elevated px-4 py-4 text-sm text-fg-muted sm:px-5">
            You’re viewing a sample portfolio so you can explore the product.{" "}
            <Link
              to="/connectors"
              className="font-medium text-fg underline-offset-4 hover:underline"
            >
              Connect your brokerage accounts
            </Link>{" "}
            to replace it with your own balances and holdings. Your data stays
            private to this workspace.
          </div>
        ) : null}

        <div className="mt-8 grid gap-3 sm:grid-cols-3">
          <StatCard
            label={hasLive ? "Total value" : "Net liquidation"}
            value={
              loading && !data
                ? "…"
                : formatUsd(
                    hasLive
                      ? totalLiveNlv
                      : (view?.workspace.latestNlv ?? null),
                  )
            }
            hint={
              hasLive
                ? `${liveAccounts.length} linked account${liveAccounts.length === 1 ? "" : "s"}`
                : view?.workspace.latestAsOf
                  ? `As of ${view.workspace.latestAsOf}`
                  : "Awaiting series"
            }
          />
          <StatCard
            label="Selected account"
            value={
              loading && !view
                ? "…"
                : formatUsd(selected?.latestNlv ?? view?.workspace.latestNlv)
            }
            hint={selected?.displayName ?? "Primary"}
          />
          <StatCard
            label="Period return"
            value={loading && !view ? "…" : formatPct(period)}
            tone={tone as "default" | "up" | "down"}
            hint="From first to last available day on the selected account"
          />
        </div>

        {data && data.accounts.length > 1 ? (
          <div className="mt-6 flex flex-wrap gap-2">
            {data.accounts.map((a) => {
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
                  <span className="ml-1 text-fg-subtle">
                    · {a.broker}
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}

        <section className="mt-8 rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-4 sm:p-6">
          <div className="mb-4">
            <h2 className="text-sm font-semibold">Account value over time</h2>
            <p className="text-xs text-fg-muted">
              {selected?.displayName ?? "Primary account"}
              {selected?.accountMask ? ` · ${selected.accountMask}` : ""}
              {selected?.isDemo ? " · sample" : ""}
            </p>
          </div>
          <NlvChart series={view?.series ?? []} />
        </section>

        <section className="mt-6 rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-4 sm:p-6">
          <h2 className="mb-4 text-sm font-semibold">Positions</h2>
          <PositionsTable positions={view?.positions ?? []} />
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
