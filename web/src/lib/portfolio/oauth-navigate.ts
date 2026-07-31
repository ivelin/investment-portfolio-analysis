/**
 * Broker OAuth must leave the Grok live-preview iframe.
 * Robinhood/Schwab set X-Frame-Options and show "content is blocked" if
 * we navigate only the iframe.
 */
export function navigateToBrokerOAuth(authorizeUrl: string): void {
  if (typeof window === "undefined") return;
  try {
    const topWin = window.top;
    if (topWin && topWin !== window) {
      topWin.location.href = authorizeUrl;
      return;
    }
  } catch {
    /* cross-origin top — fall through */
  }
  // New tab as last resort when top is inaccessible
  const opened = window.open(authorizeUrl, "_blank", "noopener,noreferrer");
  if (!opened) {
    window.location.href = authorizeUrl;
  }
}
