import { createFileRoute, Link } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";

/**
 * In-app shortcuts — always visible in the live preview (desktop + mobile).
 * Mirrors repo LINKS.md for people who don't see workspace files in chat.
 */
export const Route = createFileRoute("/links")({ component: LinksPage });

const REPO = "https://github.com/ivelin/investment-portfolio-analysis";
const MAIN = `${REPO}/tree/main`;
const LINKS_MD = `${REPO}/blob/main/web/LINKS.md`;
const AUTH_MD = `${REPO}/blob/main/web/docs/AUTH.md`;
const BRANCH = "main";

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
          Quick access to the repo and this app. Hosting notes live in{" "}
          <span className="font-medium text-fg">web/LINKS.md</span> on GitHub.
        </p>

        <Section title="Source">
          <Ext href={REPO} label="GitHub repository" />
          <Ext href={MAIN} label="Default branch: main" />
          <Ext href={LINKS_MD} label="LINKS.md on GitHub" />
          <Ext href={AUTH_MD} label="AUTH.md (Google + X social)" />
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

        <Section title="Hosting">
          <p className="text-sm text-fg-muted">
            <strong className="font-medium text-fg">Vercel + Neon</strong> is
            the production path (Google + X social auth).{" "}
            <code className="text-xs">*.grok.me</code> publish is{" "}
            <strong className="font-medium text-fg">not</strong> the live target
            (missing platform <code className="text-xs">DATABASE_URL</code>).
            Local: <code className="text-xs">npm run dev</code> on port 8080.
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
