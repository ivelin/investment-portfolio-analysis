import { Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import {
  acceptLegalPackFn,
  getLegalStatusFn,
} from "@/lib/compliance/legal-queries";
import {
  ACCEPT_SUMMARY,
  LEGAL_PACK,
  MARKET_RISK_LINE,
} from "@/lib/compliance/legal-docs";

/**
 * Low-friction gate: one screen, two links, one button.
 * Shown only when signed in and current legal pack not accepted.
 */
export function LegalGate({
  userId,
  children,
}: {
  userId: string;
  children: React.ReactNode;
}) {
  const [state, setState] = useState<
    "loading" | "need_accept" | "ok" | "error"
  >("loading");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const status = await getLegalStatusFn();
      setState(status.accepted ? "ok" : "need_accept");
    } catch {
      setState("error");
      setError("Could not verify agreements. Refresh and try again.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, userId]);

  async function onAccept() {
    setBusy(true);
    setError(null);
    try {
      const status = await acceptLegalPackFn();
      if (!status.accepted) {
        setError("Acceptance did not save. Try again.");
        setState("need_accept");
        return;
      }
      setState("ok");
    } catch {
      setError("Could not save acceptance. Try again.");
    } finally {
      setBusy(false);
    }
  }

  if (state === "loading") {
    return (
      <div className="mx-auto flex min-h-[40vh] max-w-md items-center justify-center px-4">
        <div className="h-8 w-40 animate-pulse rounded bg-bg-subtle" />
      </div>
    );
  }

  if (state === "ok") {
    return <>{children}</>;
  }

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-8rem)] w-full max-w-md flex-col justify-center px-4 py-10">
      <div className="rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-6 sm:p-7">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
          Before you continue
        </p>
        <h1 className="mt-2 text-xl font-semibold tracking-tight">
          Quick agreement
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-fg-muted">
          {ACCEPT_SUMMARY}
        </p>
        <p className="mt-3 text-xs leading-relaxed text-fg-subtle">
          {MARKET_RISK_LINE}
        </p>
        <p className="mt-4 text-sm text-fg-muted">
          Read:{" "}
          <Link
            to="/terms"
            className="font-medium text-fg underline-offset-4 hover:underline"
          >
            Terms
          </Link>
          {" · "}
          <Link
            to="/privacy"
            className="font-medium text-fg underline-offset-4 hover:underline"
          >
            Privacy
          </Link>
        </p>
        <p className="mt-2 text-[11px] text-fg-subtle">
          Version {LEGAL_PACK.version}
        </p>
        {error ? (
          <p className="mt-3 text-sm text-danger">{error}</p>
        ) : null}
        <button
          type="button"
          disabled={busy}
          onClick={() => void onAccept()}
          className="mt-6 flex h-11 w-full items-center justify-center rounded-[var(--radius-sm)] bg-primary text-sm font-medium text-primary-fg disabled:opacity-50"
        >
          {busy ? "Saving…" : "I agree — continue"}
        </button>
        <p className="mt-3 text-center text-xs text-fg-subtle">
          One step. You won’t see this again unless the terms change.
        </p>
      </div>
    </div>
  );
}
