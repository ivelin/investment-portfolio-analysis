import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, LineChart, Scale, Shield, Sprout } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { SignedIn, SignedOut } from "@/lib/auth/gates";

export const Route = createFileRoute("/")({ component: HomePage });

function HomePage() {
  return (
    <AppShell>
      <main>
        <section className="relative overflow-hidden border-b border-border/80">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,_color-mix(in_oklch,var(--color-primary)_12%,transparent),_transparent_55%)]"
          />
          <div className="relative mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-24 lg:py-28">
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-fg-subtle">
              Portfolio discipline
            </p>
            <h1 className="mt-4 max-w-3xl text-balance text-4xl font-semibold tracking-tight text-fg sm:text-5xl lg:text-[3.25rem] lg:leading-[1.1]">
              Hold yourself to the same standard you demand of every stock you
              buy.
            </h1>
            <p className="mt-5 max-w-2xl text-pretty text-base leading-relaxed text-fg-muted sm:text-lg">
              Most investors treat their brokerage accounts like a black box —
              vague “I’m doing fine” stories instead of the capital-efficiency
              and keep/cut discipline they’d apply to any single holding. This
              app exists to close that gap.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
              <SignedOut>
                <Link
                  to="/login"
                  className="inline-flex h-11 min-h-11 items-center justify-center gap-2 rounded-[var(--radius-sm)] bg-primary px-5 text-sm font-medium text-primary-fg transition-opacity hover:opacity-90"
                >
                  Open your workspace
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </SignedOut>
              <SignedIn>
                <Link
                  to="/dashboard"
                  className="inline-flex h-11 min-h-11 items-center justify-center gap-2 rounded-[var(--radius-sm)] bg-primary px-5 text-sm font-medium text-primary-fg transition-opacity hover:opacity-90"
                >
                  Go to dashboard
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </SignedIn>
              <Link
                to="/dashboard"
                className="inline-flex h-11 min-h-11 items-center gap-2 rounded-[var(--radius-sm)] border border-border bg-bg-elevated px-5 text-sm font-medium text-fg transition-colors hover:bg-bg-subtle"
              >
                Explore sample portfolio
              </Link>
            </div>
            <p className="mt-4 text-xs text-fg-subtle">
              New workspaces start with a labeled sample portfolio — no real
              balances required to try the product.
            </p>
          </div>
        </section>

        <section className="border-t border-border/80 bg-bg-elevated/40">
          <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
            <h2 className="text-sm font-medium uppercase tracking-[0.12em] text-fg-subtle">
              The problem
            </h2>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <article className="rounded-[var(--radius-lg)] border border-border bg-bg p-5 sm:p-6">
                <h3 className="text-sm font-semibold text-fg">
                  What you already do on stocks
                </h3>
                <ul className="mt-3 space-y-2 text-sm leading-relaxed text-fg-muted">
                  <li>Demand earnings quality and trend</li>
                  <li>Cut losers; add to winners</li>
                  <li>Compare to objective benchmarks</li>
                </ul>
              </article>
              <article className="rounded-[var(--radius-lg)] border border-border bg-bg p-5 sm:p-6">
                <h3 className="text-sm font-semibold text-fg">
                  What most people skip on their own accounts
                </h3>
                <ul className="mt-3 space-y-2 text-sm leading-relaxed text-fg-muted">
                  <li>Accept vague “I’m doing fine”</li>
                  <li>Leave dead weight because it feels personal</li>
                  <li>Ignore cash-flow-neutral account performance</li>
                </ul>
              </article>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
          <h2 className="text-sm font-medium uppercase tracking-[0.12em] text-fg-subtle">
            What you get
          </h2>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Outcome
              icon={<LineChart className="h-5 w-5" aria-hidden />}
              title="True performance"
              body="Time-weighted returns that neutralize deposits and withdrawals so you see skill, not cash flow noise."
            />
            <Outcome
              icon={<Scale className="h-5 w-5" aria-hidden />}
              title="Fund-like view"
              body="Treat each account like a fund: net liquidation, series, and positions in one disciplined dashboard."
            />
            <Outcome
              icon={<Sprout className="h-5 w-5" aria-hidden />}
              title="Keep / monitor / weed"
              body="Apply the same ruthless garden rules you’d apply to a watchlist — not sentiment about ‘your’ stocks."
            />
            <Outcome
              icon={<Shield className="h-5 w-5" aria-hidden />}
              title="Private by design"
              body="Your workspace is yours. Sample data is labeled. Real balances stay out of the open-source repo."
            />
          </div>
        </section>

        <section className="border-t border-border/80 bg-bg-elevated/40">
          <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16">
            <h2 className="text-sm font-medium uppercase tracking-[0.12em] text-fg-subtle">
              Privacy
            </h2>
            <p className="mt-4 max-w-2xl text-sm leading-relaxed text-fg-muted sm:text-base">
              Open source is for transparency — not for publishing anyone’s
              portfolio. Workspaces are private. Sample funds are labeled. When
              you connect a broker, that connection is only for you.{" "}
              <Link
                to="/security"
                className="font-medium text-fg underline-offset-4 hover:underline"
              >
                Read how we protect your data
              </Link>
              .
            </p>
            <div className="mt-8">
              <SignedOut>
                <Link
                  to="/login"
                  className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-sm)] bg-primary px-5 text-sm font-medium text-primary-fg transition-opacity hover:opacity-90"
                >
                  Start with a private workspace
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </SignedOut>
              <SignedIn>
                <Link
                  to="/dashboard"
                  className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-sm)] bg-primary px-5 text-sm font-medium text-primary-fg transition-opacity hover:opacity-90"
                >
                  Open dashboard
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
              </SignedIn>
            </div>
          </div>
        </section>
      </main>
    </AppShell>
  );
}

function Outcome({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
}) {
  return (
    <article className="rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-5">
      <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-sm)] border border-border bg-bg text-fg">
        {icon}
      </div>
      <h3 className="mt-4 text-sm font-semibold text-fg">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-fg-muted">{body}</p>
    </article>
  );
}
