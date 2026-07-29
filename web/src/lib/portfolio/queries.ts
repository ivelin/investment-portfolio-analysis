import { createServerFn } from "@tanstack/react-start";
import { authMiddleware } from "@/lib/auth/middleware";
import type { DashboardPayload } from "./types";

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
