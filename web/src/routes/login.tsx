import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { SOCIAL_PROVIDERS, authEnabled, signIn } from "@/lib/auth/client";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import { getAuthStatusFn } from "@/lib/auth/auth-status-queries";
import type { AuthRuntimeStatus } from "@/lib/auth/auth-runtime-status";

export const Route = createFileRoute("/login")({ component: Login });

function Login() {
  const { user, isPending } = useCurrentUserState();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<AuthRuntimeStatus | null>(null);

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
        setStatus(s);
      })
      .catch(() => {
        /* keep buttons usable when status fails */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!isPending && user) {
    return <Navigate to="/dashboard" />;
  }

  const canSignIn =
    status == null ||
    status.authEnabled ||
    status.mode === "direct_social" ||
    status.mode === "preview_client" ||
    status.mode === "deployed_client";
  const publishStoragePending = Boolean(status?.publishLikelyBroken);
  const unconfigured = status?.mode === "unconfigured";

  async function onSignIn(providerId: string) {
    setBusy(providerId);
    setError(null);
    try {
      await signIn(providerId, {
        callbackURL: "/dashboard",
        errorCallbackURL: "/login?error=signin",
      });
    } catch {
      setError(
        publishStoragePending
          ? "This published link can’t save accounts yet. Use the live preview to sign in, or attach Postgres (Neon) on the host."
          : unconfigured
            ? "Sign-in isn’t configured on this host yet."
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
                This serverless host needs durable Postgres (Neon) before sessions
                can be saved. Live preview still works with local storage.
              </p>
            </div>
          ) : null}

          {unconfigured && !publishStoragePending ? (
            <div className="mt-4 rounded-[var(--radius-md)] border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm leading-relaxed text-fg-muted">
              <p className="font-medium text-fg">Social sign-in not configured</p>
              <p className="mt-1">
                On Vercel set Google/X OAuth credentials. In the Grok sandbox,
                the shared broker should enable sign-in automatically.
              </p>
            </div>
          ) : null}

          {error ? (
            <p className="mt-4 text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}

          <div className="mt-6 space-y-3">
            {isPending && status == null ? (
              <div className="h-10 animate-pulse rounded-[var(--radius-sm)] bg-bg-subtle" />
            ) : authEnabled && canSignIn && !unconfigured ? (
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
              <p className="text-sm text-fg-muted">
                {unconfigured
                  ? "Sign-in buttons appear once auth is configured on this host."
                  : "Sign-in is disabled."}
              </p>
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
