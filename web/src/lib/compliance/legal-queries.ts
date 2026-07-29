import { createServerFn } from "@tanstack/react-start";
import { authMiddleware } from "@/lib/auth/middleware";

export const getLegalStatusFn = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async ({ context }) => {
    const { getLegalStatus } = await import("./legal.server");
    return getLegalStatus(context.userId);
  });

export const acceptLegalPackFn = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .handler(async ({ context }) => {
    const { recordLegalAcceptance } = await import("./legal.server");
    const { ensurePersonalTenant } = await import(
      "@/lib/portfolio/tenant.server"
    );
    const tenant = await ensurePersonalTenant(context.userId);
    return recordLegalAcceptance({
      userId: context.userId,
      tenantId: tenant.id,
    });
  });
