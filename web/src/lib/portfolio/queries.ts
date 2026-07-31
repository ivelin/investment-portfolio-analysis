import { createServerFn } from "@tanstack/react-start";
import { authMiddleware } from "@/lib/auth/middleware";
import type { DashboardPayload, FundSeriesPoint, PositionRow } from "./types";

export const getDashboard = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async ({ context }): Promise<DashboardPayload> => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const { getDashboardPayload } = await import("./service.server");
    const tenant = await ensurePersonalTenant(context.userId);
    return getDashboardPayload(tenant.id, {
      id: tenant.id,
      name: tenant.name,
      slug: tenant.slug,
      plan: tenant.plan,
    });
  });

export type AccountPortfolioPayload = {
  accountId: string;
  series: FundSeriesPoint[];
  positions: PositionRow[];
  periodReturnPct: number | null;
  latestNlv: number | null;
  latestAsOf: string | null;
};

export const getAccountPortfolioFn = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .validator((data: { accountId: string }) => data)
  .handler(async ({ context, data }): Promise<AccountPortfolioPayload> => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const { getAccountPortfolio } = await import("./service.server");
    const tenant = await ensurePersonalTenant(context.userId);
    const portfolio = await getAccountPortfolio(tenant.id, data.accountId);
    if (!portfolio) {
      throw new Error("Account not found");
    }
    return portfolio;
  });
