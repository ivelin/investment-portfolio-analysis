import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { DISCLAIMER_MEDIUM } from "@/lib/compliance/intended-use";

export const Route = createFileRoute("/security")({ component: SecurityPage });

function SecurityPage() {
  return (
    <AppShell>
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
          Privacy
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          Your money stays yours
        </h1>
        <p className="mt-4 text-base leading-relaxed text-fg-muted">
          This product is open source so you can inspect how it works. Real
          balances, login credentials, and personal identifiers never belong in
          the public codebase. Your workspace is private; sample data is clearly
          labeled.
        </p>

        <div className="mt-10 space-y-8">
          <Section title="Intended use">
            <p>{DISCLAIMER_MEDIUM}</p>
            <p className="mt-2">
              <Link
                to="/intended-use"
                className="font-medium text-fg underline-offset-4 hover:underline"
              >
                Read full intended use
              </Link>
            </p>
          </Section>

          <Section title="What we never put in public code">
            <ul className="list-disc space-y-2 pl-5">
              <li>Broker statements or export files</li>
              <li>Passwords, connection secrets, or API keys</li>
              <li>Database dumps with real balances</li>
              <li>Account numbers, tax IDs, or taxpayer names</li>
              <li>Screenshots or fixtures from real portfolios</li>
            </ul>
          </Section>

          <Section title="Your workspace is private">
            <ul className="list-disc space-y-2 pl-5">
              <li>
                Each signed-in user gets a personal workspace. Portfolio data is
                never mixed with other users.
              </li>
              <li>
                When you connect a broker, that connection is only for your
                workspace—and only after you’re signed in as the same person who
                started the connection.
              </li>
              <li>
                Account numbers in the UI are masked so full numbers aren’t
                shown casually.
              </li>
              <li>
                An AI agent can only see your numbers if you create a key for
                this workspace in Settings.
              </li>
            </ul>
          </Section>

          <Section title="Sample data">
            <p>
              New workspaces start with a labeled sample portfolio so you can
              explore the product without linking real accounts. Once you
              connect a broker, your own data takes over.
            </p>
          </Section>

          <Section title="Connecting brokers">
            <p>
              You approve access on the broker’s own site. We never ask for your
              brokerage password in this app. You can disconnect anytime.
            </p>
          </Section>

          <Section title="If something looks wrong">
            <p>
              Disconnect the broker, revoke any agent keys, and report the issue
              without pasting secrets into chat or public issues.
            </p>
          </Section>
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

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h2 className="text-base font-semibold text-fg">{title}</h2>
      <div className="mt-3 text-sm leading-relaxed text-fg-muted">
        {children}
      </div>
    </section>
  );
}
