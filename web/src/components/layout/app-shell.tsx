import { Link, useRouterState } from "@tanstack/react-router";
import { Shield } from "lucide-react";
import type { ReactNode } from "react";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import { authEnabled, signOut } from "@/lib/auth/client";
import { DISCLAIMER_SHORT } from "@/lib/compliance/intended-use";
import { LegalGate } from "@/components/legal/legal-gate";

/** Public legal pages — no acceptance gate (user must be able to read them). */
const LEGAL_PATH_PREFIXES = [
  "/terms",
  "/privacy",
  "/intended-use",
  "/security",
  "/login",
  "/links",
];

function pathSkipsLegalGate(pathname: string): boolean {
  if (pathname === "/") return true;
  return LEGAL_PATH_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

export function AppShell({
  children,
  bare = false,
}: {
  children: ReactNode;
  bare?: boolean;
}) {
  const { user, isPending } = useCurrentUserState();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const skipGate = pathSkipsLegalGate(pathname);

  if (bare) {
    return (
      <div className="flex min-h-dvh flex-col bg-bg text-fg">{children}</div>
    );
  }

  const body =
    user && !skipGate ? (
      <LegalGate userId={user.id}>{children}</LegalGate>
    ) : (
      children
    );

  return (
    <div className="flex min-h-dvh flex-col bg-bg text-fg">
      <header className="sticky top-0 z-40 border-b border-border/80 bg-bg/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-4 sm:gap-6">
            <Link
              to="/"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-sm)] border border-border bg-bg-elevated text-fg"
              aria-label="Home"
            >
              <span className="text-sm font-semibold tracking-tight">PA</span>
            </Link>
            <nav className="flex items-center gap-1 text-sm">
              <NavLink to="/dashboard">Dashboard</NavLink>
              <NavLink to="/connectors">Brokers</NavLink>
              {user ? <NavLink to="/settings">Settings</NavLink> : null}
            </nav>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {isPending ? (
              <div className="h-8 w-20 animate-pulse rounded bg-bg-subtle" />
            ) : user ? (
              <>
                <span className="hidden max-w-[10rem] truncate text-xs text-fg-muted sm:inline">
                  {user.displayName || user.primaryEmail || "You"}
                </span>
                <button
                  type="button"
                  onClick={() => void signOut()}
                  className="h-9 rounded-[var(--radius-sm)] border border-border px-3 text-xs font-medium text-fg-muted transition-colors hover:bg-bg-subtle hover:text-fg"
                >
                  Sign out
                </button>
              </>
            ) : authEnabled ? (
              <Link
                to="/login"
                className="inline-flex h-9 items-center rounded-[var(--radius-sm)] bg-primary px-3 text-xs font-medium text-primary-fg"
              >
                Sign in
              </Link>
            ) : null}
          </div>
        </div>
      </header>

      <div className="flex-1">{body}</div>

      <footer className="border-t border-border/80">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-xs text-fg-subtle sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="inline-flex items-center gap-1.5">
            <Shield className="h-3.5 w-3.5" aria-hidden />
            {DISCLAIMER_SHORT}
          </p>
          <p className="flex flex-wrap gap-x-2 gap-y-1">
            <Link to="/links" className="hover:text-fg hover:underline">
              Links
            </Link>
            <span aria-hidden>·</span>
            <Link to="/terms" className="hover:text-fg hover:underline">
              Terms
            </Link>
            <span aria-hidden>·</span>
            <Link to="/privacy" className="hover:text-fg hover:underline">
              Privacy
            </Link>
            <span aria-hidden>·</span>
            <Link to="/security" className="hover:text-fg hover:underline">
              Security
            </Link>
            <span aria-hidden>·</span>
            <Link to="/intended-use" className="hover:text-fg hover:underline">
              Intended use
            </Link>
          </p>
        </div>
      </footer>
    </div>
  );
}

function NavLink({
  to,
  children,
}: {
  to: "/dashboard" | "/connectors" | "/settings";
  children: ReactNode;
}) {
  return (
    <Link
      to={to}
      className="rounded-[var(--radius-sm)] px-2.5 py-1.5 text-fg-muted transition-colors hover:bg-bg-subtle hover:text-fg [&.active]:text-fg"
      activeProps={{ className: "active font-medium text-fg" }}
    >
      {children}
    </Link>
  );
}
