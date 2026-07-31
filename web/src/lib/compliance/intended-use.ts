export const PRODUCT_INTENDED_USE = {
  providesFinancialAdvice: false,
  professionalClientServices: false,
  ownAccountsOnly: true,
  audience: "retail individuals managing their own accounts",
  /** Broker connectors never place orders or move money. */
  brokerAccessMode: "read_only_analysis" as const,
  placesOrders: false,
  previewsOrders: false,
  transfersFunds: false,
} as const;

export const DISCLAIMER_SHORT =
  "For personal portfolio analysis only. Not investment advice. Read-only broker access — never places orders.";

export const DISCLAIMER_MEDIUM =
  "This product is for self-management of your own accounts. Broker connections import balances and holdings for analysis only — we never place orders, preview trades, or move money. It is not investment advice, not a recommendation to buy or sell, and not a substitute for a registered adviser.";

export const DISCLAIMER_FULL = `${DISCLAIMER_MEDIUM}

Use it to measure capital efficiency, keep/monitor/weed discipline, and reconcile your own data sources. You remain responsible for every investment decision. Markets can lose money. Past results do not guarantee future results.

We do not offer investment advice to clients, discretionary management, professional RIA tooling, or order routing. If you need advice for other people, use a licensed firm.`;

export function isProfessionalServicesFeature(flags: {
  offersAdviceToClients?: boolean;
  managesOthersMoney?: boolean;
  riaWorkflows?: boolean;
}): boolean {
  return Boolean(
    flags.offersAdviceToClients ||
      flags.managesOthersMoney ||
      flags.riaWorkflows,
  );
}
