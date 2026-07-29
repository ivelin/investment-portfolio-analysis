import { createFileRoute, Link } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import {
  LEGAL_PACK,
  MARKET_RISK_LINE,
  TERMS_SECTIONS,
} from "@/lib/compliance/legal-docs";

export const Route = createFileRoute("/terms")({ component: TermsPage });

function TermsPage() {
  return (
    <AppShell>
      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
          Legal
        </p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">
          {LEGAL_PACK.termsTitle}
        </h1>
        <p className="mt-2 text-sm text-fg-muted">
          Effective {LEGAL_PACK.effectiveDate} · Version {LEGAL_PACK.version}
        </p>
        <p className="mt-4 text-sm leading-relaxed text-fg-muted">
          {MARKET_RISK_LINE}
        </p>

        <div className="mt-10 space-y-8">
          {TERMS_SECTIONS.map((s) => (
            <section key={s.heading}>
              <h2 className="text-base font-semibold text-fg">{s.heading}</h2>
              <p className="mt-2 text-sm leading-relaxed text-fg-muted">
                {s.body}
              </p>
            </section>
          ))}
        </div>

        <p className="mt-10 text-xs leading-relaxed text-fg-subtle">
          Related:{" "}
          <Link to="/privacy" className="underline-offset-4 hover:underline">
            Privacy Policy
          </Link>
          {" · "}
          <Link
            to="/intended-use"
            className="underline-offset-4 hover:underline"
          >
            Intended use
          </Link>
        </p>
        <p className="mt-6 text-sm text-fg-muted">
          <Link to="/" className="underline-offset-4 hover:underline">
            Back to home
          </Link>
        </p>
      </main>
    </AppShell>
  );
}
