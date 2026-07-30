import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { SOCIAL_PROVIDERS, authEnabled, signIn } from "@/lib/auth/client";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import { getAuthStatusFn } from "@/lib/auth/auth-status-queries";

export const Route = createFileRoute("/login")({ component: Login });

function Login() {
  const { user, isPending } = useCurrentUserState();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  /**
   * True only when this process is real serverless published without a durable
   * DB. Live preview may forward a *.grok.me Host header but still runs PGLite
   * successfully — that must NOT show the broken banner.
   */
  const [publishStoragePending, setPublishStoragePending] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const qErr = params.get("error");
    if (qErr) {
      setError("Sign-in didn’t finish. Please try again in a moment.");
      window.history.replaceState({}, "", "/login");
    }

    let cancelled = false;
    getAuthStatusFn()
      .then((s) => {
        if (cancelled) return;
        // Fail closed only when runtime cannot use PGLite AND publish is broken.
        setPublishStoragePending(Boolean(s.publishLikelyBroken));
      })
      .catch(() => {
        /* keep buttons usable */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!isPending && user) {
    return <Navigate to="/dashboard" />;
  }

  async function onSignIn(providerId: string) {
    setBusy(providerId);
    setError(null);
    try {
      await signIn(providerId, {
        callbackURL: "/dashboard",
        errorCallbackURL: "/login?error=signin",
      });
    } catch {
      // Plain language only — no env dumps on the login screen.
      setError(
        publishStoragePending
          ? "This published link can’t save accounts yet. Use the live preview in chat to sign in, or republish after storage is attached."
          : "Sign-in didn’t work. Please try again (allow pop-ups if prompted).",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <AppShell bare>
      <main className="mx-auto flex min-h-[calc(100dvh-8rem)] w-full max-w-md flex-col justify-center px-4 py-12">
        <div className="rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-6 sm:p-8">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
            Sign in
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            Open your workspace
          </h1>
          <p className="mt-2 text-sm text-fg-muted">
            Sign in with Google or X to open a private portfolio workspace.
            You’ll start with a sample portfolio you can replace by linking your
            brokers.
          </p>

          {publishStoragePending ? (
            <div className="mt-4 rounded-[var(--radius-md)] border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm leading-relaxed text-fg-muted">
              <p className="font-medium text-fg">Published sign-in not ready yet</p>
              <p className="mt-1">
                Providers are configured, but this serverless host has no durable
                account database yet. Sign-in can’t persist sessions until storage
                is attached on publish.
              </p>
            </div>
          ) : null}

          {error ? (
            <p className="mt-4 text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}

          <div className="mt-6 space-y-3">
            {isPending ? (
              <div className="h-10 animate-pulse rounded-[var(--radius-sm)] bg-bg-subtle" />
            ) : authEnabled ? (
              SOCIAL_PROVIDERS.map((p) => (
                <button
                  key={p.providerId}
                  type="button"
                  disabled={busy != null}
                  onClick={() => void onSignIn(p.providerId)}
                  className="flex h-11 w-full items-center justify-center rounded-[var(--radius-sm)] border border-border bg-bg px-4 text-sm font-medium text-fg transition-colors hover:bg-bg-subtle disabled:opacity-50"
                >
                  {busy === p.providerId
                    ? "Opening…"
                    : `Continue with ${p.label}`}
                </button>
              ))
            ) : (
              <p className="text-sm text-fg-muted">Sign-in is disabled.</p>
            )}
          </div>

          <p className="mt-6 text-xs leading-relaxed text-fg-subtle">
            By continuing you agree to our{" "}
            <Link to="/terms" className="underline-offset-4 hover:underline">
              Terms
            </Link>{" "}
            and{" "}
            <Link to="/privacy" className="underline-offset-4 hover:underline">
              Privacy Policy
            </Link>
            . Personal analysis only — not investment advice.
          </p>
        </div>
        <p className="mt-6 text-center text-sm text-fg-muted">
          <Link to="/" className="underline-offset-4 hover:underline">
            Back to home
          </Link>
          {" · "}
          <Link to="/links" className="underline-offset-4 hover:underline">
            Project links
          </Link>
        </p>
      </main>
    </AppShell>
  );
}
