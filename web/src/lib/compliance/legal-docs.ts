export const LEGAL_PACK_VERSION = "2026-07-29";

export const LEGAL_PACK = {
  version: LEGAL_PACK_VERSION,
  effectiveDate: "July 29, 2026",
  termsTitle: "Terms of Use",
  privacyTitle: "Privacy Policy",
} as const;

export const ACCEPT_SUMMARY =
  "You agree this app is for personal portfolio analysis of your own accounts only — not investment advice, not professional client services.";

export const MARKET_RISK_LINE =
  "Investing involves risk, including possible loss of principal. Past performance does not guarantee future results.";

export const TERMS_SECTIONS = [
  {
    heading: "What this product is",
    body: "A self-management tool for analyzing your own brokerage and investment accounts. It measures capital efficiency and portfolio discipline. It is not a broker, exchange, or bank.",
  },
  {
    heading: "Not investment advice",
    body: "Nothing in the product is a recommendation to buy, sell, or hold any security. You make every decision. We do not act as an investment adviser, broker-dealer, or fiduciary.",
  },
  {
    heading: "Own accounts only",
    body: "You may only connect accounts you are authorized to access for yourself. Do not use the product to manage other people’s money as a professional service.",
  },
  {
    heading: "Your data",
    body: "Workspace data is private to your account. Open-source code never includes your balances or credentials. You can disconnect brokers and revoke API keys at any time.",
  },
  {
    heading: "Availability",
    body: "The service is provided as-is. Features may change. We may suspend access for abuse, security risk, or legal requirements.",
  },
  {
    heading: "Limitation of liability",
    body: "To the fullest extent permitted by law, we are not liable for investment losses, data delays, or decisions you make using the product.",
  },
] as const;

export const PRIVACY_SECTIONS = [
  {
    heading: "What we collect",
    body: "Account identity from sign-in (name/email), workspace settings, broker connection status, and portfolio data you choose to sync or upload.",
  },
  {
    heading: "How we use it",
    body: "To run your private workspace, compute portfolio metrics, keep connectors working, and improve reliability. We do not sell your portfolio data.",
  },
  {
    heading: "Broker connections",
    body: "OAuth tokens and API secrets are stored encrypted and never returned to the browser. Each connection is scoped to your workspace only.",
  },
  {
    heading: "Sharing",
    body: "We share data only with infrastructure providers needed to run the service, or when required by law. We do not publish individual portfolios in the public repo.",
  },
  {
    heading: "Retention",
    body: "We keep workspace data while your account is active. You may request deletion of your workspace data subject to legal holds.",
  },
  {
    heading: "Contact",
    body: "Privacy questions can be raised through the project repository maintainers for this open-source product.",
  },
] as const;
