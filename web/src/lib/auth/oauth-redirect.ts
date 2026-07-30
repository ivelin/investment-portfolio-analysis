/**
 * Pure helpers so OAuth authorize URLs never send a relative redirect_uri to
 * the Grok broker (auth.grok.me → "Invalid redirect URI").
 *
 * Better Auth builds:
 *   `${ctx.context.baseURL}/oauth2/callback/${providerId}`
 * When dynamic baseURL fails to resolve, baseURL is "" and redirect_uri becomes
 *   `/oauth2/callback/twitter`  (relative — broker rejects it)
 * Correct form for the preview client:
 *   `https://<host>/api/auth/oauth2/callback/twitter`
 */

/**
 * Turn a relative OAuth redirect_uri into an absolute app callback URL.
 * @param redirectUri value of redirect_uri query param
 * @param appOrigin e.g. https://abc.grok-sandbox.com (no path)
 */
export function absolutizeOAuthRedirectUri(
  redirectUri: string,
  appOrigin: string,
): string {
  const origin = appOrigin.replace(/\/+$/, "");
  const raw = redirectUri.trim();
  if (!raw) return raw;
  // Already absolute
  if (/^https?:\/\//i.test(raw)) return raw;
  // Relative path — ensure /api/auth prefix for Better Auth genericOAuth
  let path = raw.startsWith("/") ? raw : `/${raw}`;
  if (path.startsWith("/oauth2/")) {
    path = `/api/auth${path}`;
  } else if (!path.startsWith("/api/auth")) {
    path = `/api/auth${path.startsWith("/") ? path : `/${path}`}`;
  }
  return `${origin}${path}`;
}

/**
 * Rewrite authorize URL so redirect_uri is absolute under appOrigin.
 * No-op when already correct. Safe for Google/X social authorize URLs too.
 */
export function fixOAuthAuthorizeUrl(
  authorizeUrl: string,
  appOrigin: string,
): string {
  if (!authorizeUrl || !appOrigin) return authorizeUrl;
  try {
    const u = new URL(authorizeUrl);
    const redir = u.searchParams.get("redirect_uri");
    if (!redir) return authorizeUrl;
    const fixed = absolutizeOAuthRedirectUri(redir, appOrigin);
    if (fixed === redir) return authorizeUrl;
    u.searchParams.set("redirect_uri", fixed);
    return u.toString();
  } catch {
    return authorizeUrl;
  }
}

/** Extract origin from a Better Auth baseURL (may include /api/auth path). */
export function originFromAuthBaseURL(baseURL: string | undefined | null): string | null {
  if (!baseURL) return null;
  try {
    return new URL(baseURL).origin;
  } catch {
    return null;
  }
}
