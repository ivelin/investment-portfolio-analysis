import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  CheckCircle2,
  Copy,
  ExternalLink,
  Link2,
  Loader2,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { RedirectToSignIn } from "@/lib/auth/gates";
import { useCurrentUserState } from "@/lib/auth/use-current-user";
import {
  connectBrokerFn,
  getConnectors,
  saveSchwabAppCredentialsFn,
  type ConnectorStatus,
} from "@/lib/portfolio/connector-queries";
import {
  BROKERS,
  type BrokerId,
  isBrokerId,
} from "@/lib/portfolio/brokers/catalog";

export const Route = createFileRoute("/connectors/setup/$broker")({
  component: BrokerSetupPage,
});

function BrokerSetupPage() {
  const { broker: brokerParam } = Route.useParams();
  const { user, isPending } = useCurrentUserState();
  const [item, setItem] = useState<ConnectorStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [copied, setCopied] = useState(false);

  const broker = isBrokerId(brokerParam) ? brokerParam : null;
  const def = broker ? BROKERS[broker] : null;

  const callbackUrl = useMemo(() => {
    if (typeof window === "undefined" || !broker) return "";
    return `${window.location.origin}/api/v1/oauth/${broker}/callback`;
  }, [broker]);

  const reload = useCallback(async () => {
    if (!broker) return;
    const list = await getConnectors();
    setItem(list.find((c) => c.broker === broker) ?? null);
  }, [broker]);

  useEffect(() => {
    if (isPending || !user || !broker) return;
    let cancelled = false;
    reload().catch((err: unknown) => {
      if (cancelled) return;
      const msg = err instanceof Error ? err.message : "Failed to load";
      if (msg === "Unauthorized") setError("unauthorized");
      else setError(msg);
    });
    return () => {
      cancelled = true;
    };
  }, [user, isPending, broker, reload]);

  if (isPending) {
    return (
      <AppShell>
        <main className="mx-auto max-w-xl px-4 py-10 sm:px-6">
          <div className="h-8 w-48 animate-pulse rounded bg-bg-subtle" />
        </main>
      </AppShell>
    );
  }

  if (!user || error === "unauthorized") {
    return <RedirectToSignIn />;
  }

  if (!broker || !def) {
    return (
      <AppShell>
        <main className="mx-auto max-w-xl px-4 py-10 sm:px-6">
          <h1 className="text-2xl font-semibold">Unknown broker</h1>
          <p className="mt-2 text-sm text-fg-muted">
            That connection isn’t supported.
          </p>
          <Link
            to="/connectors"
            className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-fg underline-offset-4 hover:underline"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to brokers
          </Link>
        </main>
      </AppShell>
    );
  }

  const ready = item?.oauthConfigured === true;

  async function startOAuth() {
    if (!broker) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await connectBrokerFn({
        data: { broker, origin: window.location.origin },
      });
      if (result.kind === "oauth_redirect") {
        window.location.href = result.authorizeUrl;
        return;
      }
      setError(
        result.message ||
          "Still not ready. Complete the steps below, then try again.",
      );
      await reload();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not start connection",
      );
    } finally {
      setBusy(false);
    }
  }

  async function saveSchwabAndConnect() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await saveSchwabAppCredentialsFn({
        data: {
          clientId,
          clientSecret,
          origin: window.location.origin,
        },
      });
      setNotice("App credentials saved. Opening Schwab to approve access…");
      await reload();
      const result = await connectBrokerFn({
        data: { broker: "schwab", origin: window.location.origin },
      });
      if (result.kind === "oauth_redirect") {
        window.location.href = result.authorizeUrl;
        return;
      }
      setError(result.message);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not save credentials",
      );
    } finally {
      setBusy(false);
    }
  }

  async function copyCallback() {
    try {
      await navigator.clipboard.writeText(callbackUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Could not copy — select the callback URL manually.");
    }
  }

  return (
    <AppShell>
      <main className="mx-auto max-w-xl px-4 py-8 sm:px-6 sm:py-10">
        <Link
          to="/connectors"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-fg-muted underline-offset-4 hover:text-fg hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
          Brokers
        </Link>

        <p className="mt-6 text-xs font-medium uppercase tracking-[0.14em] text-fg-subtle">
          Connect
        </p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">
          {def.label}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-fg-muted">
          {broker === "schwab"
            ? "Finish these steps once, then approve access on Schwab. You’ll return here automatically when it’s done."
            : "Approve access on the broker’s site. You’ll return here when it’s done — balances stay in this workspace only."}
        </p>

        {ready ? (
          <div className="mt-6 flex items-start gap-2 rounded-[var(--radius-lg)] border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>
              Ready. Continue to {def.label} to approve access and import your
              accounts.
            </span>
          </div>
        ) : null}

        {notice ? (
          <p className="mt-4 text-sm text-success">{notice}</p>
        ) : null}
        {error && error !== "unauthorized" ? (
          <p className="mt-4 text-sm text-danger">{error}</p>
        ) : null}

        {broker === "schwab" ? (
          <SchwabSetup
            callbackUrl={callbackUrl}
            copied={copied}
            onCopy={() => void copyCallback()}
            clientId={clientId}
            clientSecret={clientSecret}
            setClientId={setClientId}
            setClientSecret={setClientSecret}
            ready={ready}
            busy={busy}
            onSaveAndConnect={() => void saveSchwabAndConnect()}
            onConnectOnly={() => void startOAuth()}
          />
        ) : (
          <RemoteBrokerSetup
            broker={broker}
            label={def.label}
            callbackUrl={callbackUrl}
            copied={copied}
            onCopy={() => void copyCallback()}
            ready={ready}
            busy={busy}
            onConnect={() => void startOAuth()}
          />
        )}

        <p className="mt-8 text-xs leading-relaxed text-fg-subtle">
          We never ask for your brokerage password in this app. You approve
          access on the broker’s site. Linked data stays private to this
          workspace.
        </p>
      </main>
    </AppShell>
  );
}

function SchwabSetup(props: {
  callbackUrl: string;
  copied: boolean;
  onCopy: () => void;
  clientId: string;
  clientSecret: string;
  setClientId: (v: string) => void;
  setClientSecret: (v: string) => void;
  ready: boolean;
  busy: boolean;
  onSaveAndConnect: () => void;
  onConnectOnly: () => void;
}) {
  return (
    <div className="mt-8 space-y-4">
      <Step n={1} title="Create a Schwab developer app">
        <p>
          Open the Schwab Developer portal and create an app with read access to
          accounts and positions.
        </p>
        <a
          href="https://developer.schwab.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-fg underline-offset-4 hover:underline"
        >
          Open Schwab Developer
          <ExternalLink className="h-3 w-3" aria-hidden />
        </a>
      </Step>

      <Step n={2} title="Register this callback URL">
        <p>
          Paste this exact callback URL into your Schwab app’s redirect /
          callback settings:
        </p>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
          <code className="block min-w-0 flex-1 break-all rounded-[var(--radius-sm)] border border-border bg-bg px-3 py-2 font-mono text-[11px] text-fg">
            {props.callbackUrl || "…"}
          </code>
          <button
            type="button"
            onClick={props.onCopy}
            className="inline-flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-[var(--radius-sm)] border border-border bg-bg-elevated px-3 text-xs font-medium text-fg hover:bg-bg-subtle"
          >
            <Copy className="h-3.5 w-3.5" aria-hidden />
            {props.copied ? "Copied" : "Copy"}
          </button>
        </div>
      </Step>

      <Step n={3} title="Add your app credentials">
        <p>
          From the Schwab portal, enter the Client ID and Client Secret for that
          app. They’re stored for this deployment only — never shown again in the
          UI.
        </p>
        {props.ready ? (
          <p className="mt-2 text-xs text-success">
            Credentials are already on file. You can replace them below if
            needed, or continue to Schwab.
          </p>
        ) : null}
        <label className="mt-3 block text-sm">
          <span className="text-fg-muted">Client ID</span>
          <input
            value={props.clientId}
            onChange={(e) => props.setClientId(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            className="mt-1 flex h-10 w-full rounded-[var(--radius-sm)] border border-border bg-bg px-3 font-mono text-sm text-fg outline-none focus-visible:border-fg/40"
            placeholder={props.ready ? "Leave blank to keep existing" : ""}
          />
        </label>
        <label className="mt-3 block text-sm">
          <span className="text-fg-muted">Client secret</span>
          <input
            type="password"
            value={props.clientSecret}
            onChange={(e) => props.setClientSecret(e.target.value)}
            autoComplete="new-password"
            className="mt-1 flex h-10 w-full rounded-[var(--radius-sm)] border border-border bg-bg px-3 font-mono text-sm text-fg outline-none focus-visible:border-fg/40"
            placeholder={props.ready ? "Leave blank to keep existing" : ""}
          />
        </label>
      </Step>

      <Step n={4} title="Approve access on Schwab">
        <p>
          We’ll send you to Schwab to sign in and approve read access. When you
          finish, Schwab returns you here and we import balances into this
          workspace only.
        </p>
      </Step>

      <div className="flex flex-col gap-3 pt-2">
        {props.clientId.trim() && props.clientSecret.trim() ? (
          <button
            type="button"
            disabled={props.busy}
            onClick={props.onSaveAndConnect}
            className="inline-flex h-11 min-h-11 w-full items-center justify-center gap-2 rounded-[var(--radius-sm)] bg-primary px-4 text-sm font-medium text-primary-fg disabled:opacity-50"
          >
            {props.busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Link2 className="h-4 w-4" />
            )}
            Save & continue to Schwab
          </button>
        ) : props.ready ? (
          <button
            type="button"
            disabled={props.busy}
            onClick={props.onConnectOnly}
            className="inline-flex h-11 min-h-11 w-full items-center justify-center gap-2 rounded-[var(--radius-sm)] bg-primary px-4 text-sm font-medium text-primary-fg disabled:opacity-50"
          >
            {props.busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Link2 className="h-4 w-4" />
            )}
            Continue to Schwab
          </button>
        ) : (
          <p className="text-center text-xs text-fg-subtle">
            Enter Client ID and secret above to unlock the next step.
          </p>
        )}
      </div>
    </div>
  );
}

function RemoteBrokerSetup(props: {
  broker: BrokerId;
  label: string;
  callbackUrl: string;
  copied: boolean;
  onCopy: () => void;
  ready: boolean;
  busy: boolean;
  onConnect: () => void;
}) {
  return (
    <div className="mt-8 space-y-4">
      <Step n={1} title={`Have a ${props.label} account ready`}>
        <p>You’ll sign in with the account you want to analyze.</p>
      </Step>
      <Step n={2} title="Approve access">
        <p>
          Tap continue. {props.label} will ask you to approve read access for
          portfolio analysis.
        </p>
        <p className="mt-2 text-xs text-fg-subtle">
          Callback used by this app:{" "}
          <button
            type="button"
            onClick={props.onCopy}
            className="font-mono text-fg underline-offset-2 hover:underline"
          >
            {props.copied ? "Copied!" : props.callbackUrl || "…"}
          </button>
        </p>
      </Step>
      <Step n={3} title="Return here">
        <p>
          After approval, you’ll land back on Brokers with your accounts linked
          to this workspace only.
        </p>
      </Step>
      <button
        type="button"
        disabled={props.busy || !props.ready}
        onClick={props.onConnect}
        className="mt-2 inline-flex h-11 min-h-11 w-full items-center justify-center gap-2 rounded-[var(--radius-sm)] bg-primary px-4 text-sm font-medium text-primary-fg disabled:opacity-50"
      >
        {props.busy ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Link2 className="h-4 w-4" />
        )}
        {props.ready
          ? `Continue to ${props.label}`
          : `${props.label} isn’t ready yet — try again shortly`}
      </button>
    </div>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-3 rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-bg text-xs font-semibold text-fg">
        {n}
      </span>
      <div className="min-w-0 text-sm leading-relaxed text-fg-muted">
        <p className="font-medium text-fg">{title}</p>
        <div className="mt-1">{children}</div>
      </div>
    </div>
  );
}
