import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, KeyRound, Trash2 } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { RedirectToSignIn } from "@/lib/auth/gates";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import {
  createApiKeyFn,
  listApiKeysFn,
  revokeApiKeyFn,
  type ApiKeyPublic,
} from "@/lib/portfolio/api-key-queries";

export const Route = createFileRoute("/settings")({
  component: SettingsPage,
});

function SettingsPage() {
  const { user, isPending } = useCurrentUserState();
  const [keys, setKeys] = useState<ApiKeyPublic[]>([]);
  const [name, setName] = useState("Agent key");
  const [rawOnce, setRawOnce] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    const list = await listApiKeysFn();
    setKeys(list.filter((k) => !k.revokedAt));
  }, []);

  useEffect(() => {
    if (isPending || !user) return;
    let cancelled = false;
    setError(null);
    reload().catch((err: unknown) => {
      if (cancelled) return;
      const msg = err instanceof Error ? err.message : "Failed to load";
      if (msg === "Unauthorized") setError("unauthorized");
      else setError(msg);
    });
    return () => {
      cancelled = true;
    };
  }, [user, isPending, reload]);

  if (isPending) {
    return (
      <AppShell>
        <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
          <div className="h-8 w-48 animate-pulse rounded bg-bg-subtle" />
        </main>
      </AppShell>
    );
  }

  if (!user || error === "unauthorized") {
    return <RedirectToSignIn />;
  }

  return (
    <AppShell>
      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
          Settings
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          Agent access
        </h1>
        <p className="mt-2 max-w-xl text-sm leading-relaxed text-fg-muted">
          Create an API key so an AI assistant can read the same portfolio view
          you see in this app — only for{" "}
          <strong className="font-medium text-fg">your</strong> workspace.
        </p>

        {error && error !== "unauthorized" ? (
          <div className="mt-6 flex gap-2 rounded-[var(--radius-md)] border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}
        {notice ? (
          <div className="mt-6 flex gap-2 rounded-[var(--radius-md)] border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{notice}</span>
          </div>
        ) : null}

        {rawOnce ? (
          <div className="mt-6 rounded-[var(--radius-lg)] border border-warning/40 bg-warning/10 px-4 py-4 text-sm">
            <p className="font-medium text-fg">Copy this key now — shown once</p>
            <code className="mt-2 block break-all rounded bg-bg px-3 py-2 font-mono text-xs text-fg">
              {rawOnce}
            </code>
            <p className="mt-2 text-xs text-fg-muted">
              Keep it private. Anyone with the key can read this workspace’s
              portfolio summary.
            </p>
          </div>
        ) : null}

        <div className="mt-8 rounded-[var(--radius-xl)] border border-border bg-bg-elevated p-5 sm:p-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex-1 text-sm">
              <span className="text-fg-muted">Key name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 flex h-10 w-full rounded-[var(--radius-sm)] border border-border bg-bg px-3 text-sm text-fg outline-none focus-visible:border-fg/40"
              />
            </label>
            <button
              type="button"
              disabled={busy || !name.trim()}
              onClick={() => {
                setBusy(true);
                setError(null);
                setNotice(null);
                setRawOnce(null);
                createApiKeyFn({ data: { name: name.trim() } })
                  .then(async (res) => {
                    setRawOnce(res.rawKey);
                    setNotice("API key created for this workspace only.");
                    await reload();
                  })
                  .catch((err: unknown) => {
                    setError(
                      err instanceof Error ? err.message : "Could not create key",
                    );
                  })
                  .finally(() => setBusy(false));
              }}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-[var(--radius-sm)] bg-primary px-4 text-sm font-medium text-primary-fg disabled:opacity-40"
            >
              <KeyRound className="h-4 w-4" aria-hidden />
              Create key
            </button>
          </div>
        </div>

        <div className="mt-6 space-y-3">
          {keys.length === 0 ? (
            <p className="text-sm text-fg-muted">No API keys yet.</p>
          ) : (
            keys.map((k) => (
              <div
                key={k.id}
                className="flex items-center justify-between gap-3 rounded-[var(--radius-lg)] border border-border bg-bg-elevated px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-fg">
                    {k.name}
                  </p>
                  <p className="text-xs text-fg-subtle">
                    ···{k.keyPrefix}
                    {k.lastUsedAt
                      ? ` · last used ${new Date(k.lastUsedAt).toLocaleDateString()}`
                      : " · never used"}
                  </p>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    revokeApiKeyFn({ data: { keyId: k.id } })
                      .then(async () => {
                        setNotice("Key revoked.");
                        await reload();
                      })
                      .catch((err: unknown) => {
                        setError(
                          err instanceof Error
                            ? err.message
                            : "Could not revoke key",
                        );
                      })
                      .finally(() => setBusy(false));
                  }}
                  className="inline-flex h-9 items-center gap-1.5 rounded-[var(--radius-sm)] border border-border px-3 text-xs font-medium text-fg-muted hover:bg-bg-subtle"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  Revoke
                </button>
              </div>
            ))
          )}
        </div>

        <p className="mt-8 text-sm text-fg-muted">
          <Link
            to="/connectors"
            className="font-medium text-fg underline-offset-4 hover:underline"
          >
            Connect brokers
          </Link>{" "}
          to replace sample data with your accounts.
        </p>
      </main>
    </AppShell>
  );
}
