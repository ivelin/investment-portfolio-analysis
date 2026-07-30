/**
 * Sign-in providers offered in the product UI (Google + X only).
 *
 * Source of truth for BOTH server config and client buttons. Dependency-free
 * so the client can import without pulling Better Auth / pg into the browser.
 *
 * - Direct social (Vercel / any host with GOOGLE_* / TWITTER_*): Better Auth
 *   `socialProviders` use `providerId` as the social id (`google` | `twitter`).
 * - Grok broker (sandbox / local only, never Vercel): optional legacy path
 *   maps `providerId` → broker `idp` via `brokerIdp`.
 */

export type SocialProvider = {
  /** Better Auth social id and button key. */
  providerId: "google" | "twitter";
  /** Human label for the sign-in button. */
  label: string;
  /**
   * Grok broker upstream id (legacy sandbox only). Unused for direct social.
   * Better Auth’s X id remains `twitter`.
   */
  brokerIdp: string;
};

/** Social-only catalog — no email/password. */
export const SOCIAL_PROVIDERS: readonly SocialProvider[] = [
  { providerId: "google", label: "Google", brokerIdp: "google" },
  { providerId: "twitter", label: "X", brokerIdp: "twitter" },
];

/** @deprecated Use SOCIAL_PROVIDERS — kept as alias for gradual renames. */
export const GROK_PROVIDERS = SOCIAL_PROVIDERS;

export function isSocialProviderId(
  id: string,
): id is SocialProvider["providerId"] {
  return id === "google" || id === "twitter";
}
