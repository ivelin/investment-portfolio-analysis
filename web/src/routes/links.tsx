import { createFileRoute, Link } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";

/**
 * In-app shortcuts — always visible in the live preview (desktop + mobile).
 * Mirrors repo LINKS.md for people who don't see workspace files in chat.
 */
export const Route = createFileRoute("/links")({ component: LinksPage });

const REPO = "https://github.com/ivelin/investment-portfolio-analysis";
const PR = `${REPO}/pull/5`;
const LINKS_MD = `${REPO}/blob/feature/multi-tenant-platform/LINKS.md`;
const BRANCH = "feature/multi-tenant-platform";

function LinksPage() {
  return (
    <AppShell>
      <main className="mx-auto max-w-xl px-4 py-10 sm:px-6">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
          Shortcuts
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
          Project links
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-fg-muted">
          Quick access to the repo and this app. Same list lives in GitHub as{" "}
          <span className="font-medium text-fg">LINKS.md</span> on the feature
          branch.
        </p>

        <Section title="Source">
          <Ext href={REPO} label="GitHub repository" />
          <Ext href={PR} label="Pull request #5 (multi-tenant)" />
          <Ext href={LINKS_MD} label="LINKS.md on GitHub" />
          <p className="text-xs text-fg-subtle">Branch: {BRANCH}</p>
        </Section>

        <Section title="In this app">
          <Int to="/dashboard" label="Dashboard" />
          <Int to="/connectors" label="Brokers" />
          <Int to="/settings" label="Settings" />
          <Int to="/terms" label="Terms" />
          <Int to="/privacy" label="Privacy" />
          <Int to="/intended-use" label="Intended use" />
          <Int to="/security" label="Security" />
        </Section>

        <Section title="Live preview">
          <p className="text-sm text-fg-muted">
            Open the <strong className="font-medium text-fg">live preview</strong>{" "}
            panel in this Grok conversation (desktop: usually beside or below the
            chat). That is the running app for this session.
          </p>
        </Section>

        <p className="mt-10 text-sm text-fg-muted">
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
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <h2 className="text-sm font-semibold text-fg">{title}</h2>
      <div className="mt-3 space-y-2">{children}</div>
    </section>
  );
}

function Ext({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 text-sm font-medium text-fg underline-offset-4 hover:underline"
    >
      {label}
      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-fg-subtle" aria-hidden />
    </a>
  );
}

function Int({
  to,
  label,
}: {
  to:
    | "/dashboard"
    | "/connectors"
    | "/settings"
    | "/terms"
    | "/privacy"
    | "/intended-use"
    | "/security";
  label: string;
}) {
  return (
    <Link
      to={to}
      className="block text-sm font-medium text-fg underline-offset-4 hover:underline"
    >
      {label}
    </Link>
  );
}
