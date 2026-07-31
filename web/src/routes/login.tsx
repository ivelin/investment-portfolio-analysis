import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import {
  SOCIAL_PROVIDERS,
  authClient,
  authEnabled,
  signIn,
} from "@/lib/auth/client";
import { emailAndPasswordEnabled } from "@/lib/auth/email-password";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import { getAuthStatusFn } from "@/lib/auth/auth-status-queries";
import type { AuthRuntimeStatus } from "@/lib/auth/auth-runtime-status";

export const Route = createFileRoute("/login")({ component: Login });

function Login() {
  const { user, isPending } = useCurrentUserState();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<AuthRuntimeStatus | null>(null);
  const [emailMode, setEmailMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const qErr = params.get("error");
    if (qErr) {
      setError(
        qErr === "redirect_uri"
          ? "Google/X sign-in is blocked until Grok registers this app’s callback URLs on the auth broker. Use email below, or try the live preview for social sign-in."
          : "Sign-in didn’t finish. Try email below, or social again in a moment.",
      );
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
  const isGrokPublished = status?.hostKind === "published";
  const showSocial =
    authEnabled && canSignIn && !unconfigured && !publishStoragePending;
  const showEmail =
    emailAndPasswordEnabled &&
    authEnabled &&
    !publishStoragePending &&
    !unconfigured;

  async function onSocial(providerId: string) {
    setBusy(providerId);
    setError(null);
    try {
      await signIn(providerId, {
        callbackURL: "/dashboard",
        errorCallbackURL: "/login?error=signin",
      });
    } catch {
      setError(
        isGrokPublished
          ? "Google/X via Grok auth failed (often “Invalid redirect URI” — the platform must allow this app’s callback URLs). Use email & password below for now."
          : "Sign-in didn’t work. Please try again (allow pop-ups if prompted).",
      );
    } finally {
      setBusy(null);
    }
  }

  async function onEmail(e: React.FormEvent) {
    e.preventDefault();
    setBusy("email");
    setError(null);
    const trimmed = email.trim().toLowerCase();
    if (!trimmed || password.length < 8) {
      setError("Use a valid email and a password of at least 8 characters.");
      setBusy(null);
      return;
    }
    try {
      if (emailMode === "signup") {
        const res = await authClient.signUp.email({
          email: trimmed,
          password,
          name: name.trim() || trimmed.split("@")[0] || "Investor",
          callbackURL: "/dashboard",
        });
        if (res.error) {
          throw new Error(res.error.message || "Sign-up failed");
        }
      } else {
        const res = await authClient.signIn.email({
          email: trimmed,
          password,
          callbackURL: "/dashboard",
        });
        if (res.error) {
          throw new Error(res.error.message || "Sign-in failed");
        }
      }
      window.location.href = "/dashboard";
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : emailMode === "signup"
            ? "Could not create account."
            : "Could not sign in with email.",
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
            Sign in to open a private portfolio workspace. You’ll start with a
            sample portfolio you can replace by linking brokers.
          </p>

          {isGrokPublished ? (
            <div className="mt-4 rounded-[var(--radius-md)] border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm leading-relaxed text-fg-muted">
              <p className="font-medium text-fg">Google / X on this published host</p>
              <p className="mt-1">
                If you see <strong className="text-fg">Invalid redirect URI</strong> on
                auth.grok.me, that is a Grok deploy provisioning gap: the auth
                broker client was created without this app’s callback URLs. The
                app cannot register those. Use <strong className="text-fg">email
                & password</strong> below (works now), or social sign-in in the
                live preview.
              </p>
              {status?.expectedBrokerRedirectUris?.length ? (
                <p className="mt-2 text-xs text-fg-subtle break-all">
                  Platform must allow:{" "}
                  {status.expectedBrokerRedirectUris.join(" · ")}
                </p>
              ) : null}
            </div>
          ) : null}

          {publishStoragePending ? (
            <div className="mt-4 rounded-[var(--radius-md)] border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm leading-relaxed text-fg-muted">
              <p className="font-medium text-fg">Storage not ready</p>
              <p className="mt-1">
                This deployment has no durable database yet. Re-publish from
                Grok so storage can be provisioned.
              </p>
            </div>
          ) : null}

          {error ? (
            <p className="mt-4 text-sm text-danger" role="alert">
              {error}
            </p>
          ) : null}

          {showSocial ? (
            <div className="mt-6 space-y-3">
              {SOCIAL_PROVIDERS.map((p) => (
                <button
                  key={p.providerId}
                  type="button"
                  disabled={busy != null}
                  onClick={() => void onSocial(p.providerId)}
                  className="flex h-11 w-full items-center justify-center rounded-[var(--radius-sm)] border border-border bg-bg px-4 text-sm font-medium text-fg transition-colors hover:bg-bg-subtle disabled:opacity-50"
                >
                  {busy === p.providerId
                    ? "Opening…"
                    : `Continue with ${p.label}`}
                </button>
              ))}
            </div>
          ) : null}

          {showEmail ? (
            <div className={showSocial ? "mt-6" : "mt-6"}>
              {showSocial ? (
                <div className="mb-4 flex items-center gap-3 text-xs text-fg-subtle">
                  <div className="h-px flex-1 bg-border" />
                  <span>or email</span>
                  <div className="h-px flex-1 bg-border" />
                </div>
              ) : null}
              <form onSubmit={(e) => void onEmail(e)} className="space-y-3">
                {emailMode === "signup" ? (
                  <label className="block text-sm">
                    <span className="text-fg-muted">Name</span>
                    <input
                      type="text"
                      autoComplete="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="mt-1 h-11 w-full rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-fg outline-none focus:border-fg-subtle"
                    />
                  </label>
                ) : null}
                <label className="block text-sm">
                  <span className="text-fg-muted">Email</span>
                  <input
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="mt-1 h-11 w-full rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-fg outline-none focus:border-fg-subtle"
                  />
                </label>
                <label className="block text-sm">
                  <span className="text-fg-muted">Password</span>
                  <input
                    type="password"
                    required
                    minLength={8}
                    autoComplete={
                      emailMode === "signup" ? "new-password" : "current-password"
                    }
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="mt-1 h-11 w-full rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-fg outline-none focus:border-fg-subtle"
                  />
                </label>
                <button
                  type="submit"
                  disabled={busy != null}
                  className="flex h-11 w-full items-center justify-center rounded-[var(--radius-sm)] bg-fg px-4 text-sm font-medium text-bg transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {busy === "email"
                    ? "Working…"
                    : emailMode === "signup"
                      ? "Create account"
                      : "Sign in with email"}
                </button>
              </form>
              <p className="mt-3 text-center text-xs text-fg-muted">
                {emailMode === "signin" ? (
                  <>
                    No account?{" "}
                    <button
                      type="button"
                      className="underline-offset-4 hover:underline"
                      onClick={() => setEmailMode("signup")}
                    >
                      Create one
                    </button>
                  </>
                ) : (
                  <>
                    Already have an account?{" "}
                    <button
                      type="button"
                      className="underline-offset-4 hover:underline"
                      onClick={() => setEmailMode("signin")}
                    >
                      Sign in
                    </button>
                  </>
                )}
              </p>
            </div>
          ) : null}

          {!showSocial && !showEmail ? (
            <p className="mt-6 text-sm text-fg-muted">
              {publishStoragePending
                ? "Sign-in is paused until storage is provisioned."
                : unconfigured
                  ? "Sign-in isn’t configured on this host yet."
                  : "Sign-in is disabled."}
            </p>
          ) : null}

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
