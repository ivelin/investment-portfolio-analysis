/**
 * Pure helpers so OAuth authorize URLs sent to the Grok broker (auth.grok.me)
 * always carry:
 *   1. absolute redirect_uri under this app's origin
 *   2. idp=google|twitter (broker requires it for headless upstream)
 *   3. prompt=login (force account chooser)
 *
 * Better Auth builds:
 *   `${ctx.context.baseURL}/oauth2/callback/${providerId}`
 * When dynamic baseURL fails, redirect_uri becomes relative
 *   `/oauth2/callback/twitter`
 * which auth.grok.me may reject as "Invalid redirect URI" once a broker
 * session exists (exact match against client.redirectUrls).
 *
 * Correct form:
 *   `https://<host>/api/auth/oauth2/callback/twitter`
 */

const IDP_FROM_CALLBACK =
  /\/oauth2\/callback\/(google|twitter)(?:\?|#|$)/i;
const IDP_FROM_SOCIAL_CALLBACK =
  /\/callback\/(google|twitter)(?:\?|#|$)/i;

/**
 * Canonical app callback URL for a provider (what the broker must have
 * registered on the per-app GROK_AUTH client).
 */
export function appOAuthCallbackUrl(
  appOrigin: string,
  providerId: "google" | "twitter" | string,
): string {
  const origin = appOrigin.replace(/\/+$/, "");
  return `${origin}/api/auth/oauth2/callback/${providerId}`;
}

/**
 * Turn a relative OAuth redirect_uri into an absolute app callback URL.
 */
export function absolutizeOAuthRedirectUri(
  redirectUri: string,
  appOrigin: string,
): string {
  const origin = appOrigin.replace(/\/+$/, "");
  const raw = redirectUri.trim();
  if (!raw) return raw;
  if (/^https?:\/\//i.test(raw)) {
    // Already absolute — still normalize accidental /oauth2 without /api/auth
    try {
      const u = new URL(raw);
      if (u.pathname.startsWith("/oauth2/")) {
        u.pathname = `/api/auth${u.pathname}`;
        return u.toString();
      }
      return raw;
    } catch {
      return raw;
    }
  }
  let path = raw.startsWith("/") ? raw : `/${raw}`;
  if (path.startsWith("/oauth2/")) {
    path = `/api/auth${path}`;
  } else if (!path.startsWith("/api/auth")) {
    path = `/api/auth${path.startsWith("/") ? path : `/${path}`}`;
  }
  return `${origin}${path}`;
}

function inferIdpFromRedirectUri(redirectUri: string): string | null {
  const m =
    redirectUri.match(IDP_FROM_CALLBACK) ||
    redirectUri.match(IDP_FROM_SOCIAL_CALLBACK);
  return m?.[1]?.toLowerCase() ?? null;
}

/**
 * Rewrite authorize URL so redirect_uri is absolute and broker idp/prompt are set.
 * Safe for Google/X social authorize URLs too (no-op on non-broker hosts).
 */
export function fixOAuthAuthorizeUrl(
  authorizeUrl: string,
  appOrigin: string,
  opts?: { providerId?: string },
): string {
  if (!authorizeUrl || !appOrigin) return authorizeUrl;
  try {
    const u = new URL(authorizeUrl);
    const redir = u.searchParams.get("redirect_uri");
    if (redir) {
      const fixed = absolutizeOAuthRedirectUri(redir, appOrigin);
      if (fixed !== redir) u.searchParams.set("redirect_uri", fixed);
    }

    // Only enforce idp/prompt on the Grok broker authorize endpoint.
    const isBroker =
      u.hostname === "auth.grok.me" ||
      u.pathname.includes("/oauth2/authorize");
    if (isBroker) {
      if (!u.searchParams.get("idp")) {
        const fromRedir = redir
          ? inferIdpFromRedirectUri(
              u.searchParams.get("redirect_uri") || redir,
            )
          : null;
        const idp =
          opts?.providerId ||
          fromRedir ||
          null;
        if (idp) u.searchParams.set("idp", idp);
      }
      if (!u.searchParams.get("prompt")) {
        u.searchParams.set("prompt", "login");
      }
    }
    return u.toString();
  } catch {
    return authorizeUrl;
  }
}

/** Extract origin from a Better Auth baseURL (may include /api/auth path). */
export function originFromAuthBaseURL(
  baseURL: string | undefined | null,
): string | null {
  if (!baseURL) return null;
  try {
    return new URL(baseURL).origin;
  } catch {
    return null;
  }
}

/**
 * Redirect URIs the Grok deployer must register on the per-app OAuth client.
 * Exact match required by better-auth OIDC (`client.redirectUrls`).
 */
export function expectedBrokerRedirectUris(appOrigin: string): string[] {
  const origin = appOrigin.replace(/\/+$/, "");
  return [
    appOAuthCallbackUrl(origin, "google"),
    appOAuthCallbackUrl(origin, "twitter"),
  ];
}
