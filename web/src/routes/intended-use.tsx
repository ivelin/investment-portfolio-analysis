import { createFileRoute, Link } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import {
  DISCLAIMER_FULL,
  DISCLAIMER_MEDIUM,
  PRODUCT_INTENDED_USE,
} from "@/lib/compliance/intended-use";

export const Route = createFileRoute("/intended-use")({
  component: IntendedUsePage,
});

function IntendedUsePage() {
  return (
    <AppShell>
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
          Intended use
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          For your own portfolio—not advice for others
        </h1>
        <p className="mt-4 text-base leading-relaxed text-fg-muted">
          {DISCLAIMER_MEDIUM}
        </p>

        <div className="mt-10 space-y-6 text-sm leading-relaxed text-fg-muted">
          <section>
            <h2 className="text-base font-semibold text-fg">Who it’s for</h2>
            <p className="mt-2">
              Retail investors who want a clearer picture of{" "}
              <strong className="font-medium text-fg">their own</strong>{" "}
              accounts—performance, positions, and discipline tools—in a private
              workspace.
            </p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-fg">Who it’s not for</h2>
            <ul className="mt-2 list-disc space-y-2 pl-5">
              <li>Anyone offering investment advice or portfolio management to clients</li>
              <li>RIAs, advisors, or firms analyzing third-party accounts as a service</li>
              <li>Sharing one login to manage other people’s money</li>
            </ul>
          </section>

          <section>
            <h2 className="text-base font-semibold text-fg">Not advice</h2>
            <p className="mt-2">
              Nothing in this app is a recommendation to buy, sell, or hold any
              security. Numbers can be delayed or incomplete. Decisions are
              yours.
            </p>
          </section>

          <section>
            <h2 className="text-base font-semibold text-fg">Your data</h2>
            <p className="mt-2">
              Workspaces are isolated. You connect brokers only for accounts
              you’re allowed to access for yourself. See{" "}
              <Link
                to="/security"
                className="font-medium text-fg underline-offset-4 hover:underline"
              >
                Privacy
              </Link>
              .
            </p>
          </section>

          <p className="rounded-[var(--radius-lg)] border border-border bg-bg-elevated px-4 py-3 text-xs text-fg-subtle">
            {DISCLAIMER_FULL}
          </p>
          <p className="text-xs text-fg-subtle">
            Product mode: {PRODUCT_INTENDED_USE.audience.replace(/_/g, " ")}.
          </p>
        </div>

        <p className="mt-12 text-sm text-fg-muted">
          <Link to="/" className="underline-offset-4 hover:underline">
            Back to home
          </Link>
        </p>
      </main>
    </AppShell>
  );
}
