/**
 * Local email/password sign-in (this app's Better Auth DB — not the broker).
 *
 * Enabled so published *.grok.me stays usable when the platform Grok auth
 * broker client is missing registered redirect_uris (Invalid redirect URI).
 * Social (Google/X via auth.grok.me) remains preferred when the broker works
 * (live preview + correctly provisioned publish).
 *
 * Do NOT edit `server.ts` for this flag — import only.
 */
export const emailAndPasswordEnabled = true;
