import { genericOAuthClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";
import { isSocialProviderId } from "./providers";
import { fixOAuthAuthorizeUrl } from "./oauth-redirect";

/**
 * Better Auth client for this React SPA (browser-side).
 *
 * Talks to this app's OWN Better Auth at same-origin `/api/auth/*`.
 * - Direct social (GOOGLE_ / TWITTER_ env): signIn.social → Google or X
 * - Grok broker (sandbox / CLI / non-Vercel): signIn.oauth2 → auth.grok.me
 * Live-preview iframe uses popup + /auth/popup so cookies stay first-party.
 */
export const authClient = createAuthClient({
  plugins: [genericOAuthClient()],
  fetchOptions: {
    onRequest(ctx) {
      const token = getBearerToken();
      if (token) ctx.headers.set("Authorization", `Bearer ${token}`);
      return ctx;
    },
  },
});

/**
 * True when sign-in UI should be shown. Off only with VITE_AUTH_ENABLED=false.
 */
export const authEnabled = import.meta.env.VITE_AUTH_ENABLED !== "false";

/** Providers for login buttons (Google + X only). */
export { SOCIAL_PROVIDERS, GROK_PROVIDERS } from "./providers";

const BEARER_KEY = "grok-auth.bearer-token";

export function getBearerToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(BEARER_KEY);
  } catch {
    return null;
  }
}

function setBearerToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.sessionStorage.setItem(BEARER_KEY, token);
    else window.sessionStorage.removeItem(BEARER_KEY);
  } catch {
    /* ignore */
  }
}

function inLivePreview(): boolean {
  return (
    typeof window !== "undefined" &&
    window.location.hostname.endsWith(".grok-sandbox.com")
  );
}

type PopupMessage = {
  source: "grok-auth-popup";
  token: string | null;
  error?: string;
};

function withAbsoluteRedirect(url: string, providerId?: string): string {
  if (typeof window === "undefined") return url;
  return fixOAuthAuthorizeUrl(url, window.location.origin, { providerId });
}

/**
 * Start sign-in with Google or X (`providerId`: `google` | `twitter`).
 *
 * - Direct social: full-page signIn.social → Google/X authorize.
 * - Grok broker: signIn.oauth2 → auth.grok.me (absolute redirect_uri + idp).
 * - Live-preview iframe: popup to /auth/popup.
 */
export async function signIn(
  providerId: string,
  opts: { callbackURL?: string; errorCallbackURL?: string } = {},
): Promise<void> {
  if (!isSocialProviderId(providerId)) {
    throw new Error("Unknown sign-in provider");
  }
  const callbackURL = opts.callbackURL ?? "/";
  const errorCallbackURL = opts.errorCallbackURL ?? "/";

  const popup = inLivePreview() ? openSignInPopup(providerId) : null;

  const hadBearer = Boolean(getBearerToken());
  if (hadBearer || !inLivePreview()) {
    try {
      await authClient.signOut();
    } catch {
      /* proceed */
    }
  }
  setBearerToken(null);

  if (inLivePreview()) {
    if (!popup) throw new Error("Pop-up blocked — allow pop-ups for sign-in");
    const token = await waitForPopupToken(popup);
    if (!token) throw new Error("Sign-in was cancelled or failed");
    setBearerToken(token);
    try {
      await authClient.getSession();
    } catch {
      /* recover later */
    }
    if (typeof window !== "undefined") {
      const dest = new URL(callbackURL, window.location.origin);
      const here = window.location;
      if (
        dest.origin !== here.origin ||
        dest.pathname !== here.pathname ||
        dest.search !== here.search
      ) {
        window.location.href = callbackURL;
      }
    }
    return;
  }

  // Prefer direct social. On grok_broker hosts socialProviders is empty, so
  // social fails — fall through to generic oauth2 (do not throw first).
  const social = await authClient.signIn.social({
    provider: providerId,
    callbackURL,
    errorCallbackURL,
  });
  if (!social.error) {
    if (social.data?.url) {
      window.location.href = withAbsoluteRedirect(
        social.data.url,
        providerId,
      );
    }
    return;
  }

  // Grok broker (sandbox / CLI / published *.grok.me)
  const oauth2 = await authClient.signIn.oauth2({
    providerId,
    callbackURL,
    errorCallbackURL,
  });
  if (oauth2.error) {
    throw new Error(
      oauth2.error.message ?? social.error.message ?? "Sign-in failed",
    );
  }
  if (oauth2.data?.url) {
    window.location.href = withAbsoluteRedirect(oauth2.data.url, providerId);
  }
}

function openSignInPopup(providerId: string): Window | null {
  const origin = window.location.origin;
  const url = `${origin}/auth/popup?providerId=${encodeURIComponent(providerId)}`;
  const name = `grok-signin-${Date.now()}`;
  return window.open(url, name, "popup,width=500,height=650");
}

function waitForPopupToken(popup: Window): Promise<string | null> {
  return new Promise((resolve) => {
    const started = Date.now();
    const timer = window.setInterval(() => {
      if (popup.closed || Date.now() - started > 120_000) {
        window.clearInterval(timer);
        window.removeEventListener("message", onMessage);
        resolve(null);
      }
    }, 400);

    function onMessage(ev: MessageEvent) {
      if (ev.origin !== window.location.origin) return;
      const data = ev.data as PopupMessage | null;
      if (!data || data.source !== "grok-auth-popup") return;
      window.clearInterval(timer);
      window.removeEventListener("message", onMessage);
      try {
        popup.close();
      } catch {
        /* ignore */
      }
      resolve(data.token);
    }
    window.addEventListener("message", onMessage);
  });
}

export async function signOut(): Promise<void> {
  setBearerToken(null);
  try {
    await authClient.signOut();
  } catch {
    /* ignore */
  }
  if (typeof window !== "undefined") {
    window.location.href = "/";
  }
}
