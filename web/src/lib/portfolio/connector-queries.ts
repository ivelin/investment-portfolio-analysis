import { createServerFn } from "@tanstack/react-start";
import { authMiddleware } from "@/lib/auth/middleware";
import type { BrokerId } from "./brokers/catalog";
import type { ConnectorPublic } from "./connectors.server";

export type ConnectorStatus = ConnectorPublic;

export const getConnectors = createServerFn({ method: "GET" })
  .middleware([authMiddleware])
  .handler(async ({ context }): Promise<ConnectorStatus[]> => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const { listConnectors } = await import("./connectors.server");
    const tenant = await ensurePersonalTenant(context.userId);
    return listConnectors(tenant.id);
  });

export const connectBrokerFn = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((data: { broker: BrokerId; origin?: string }) => data)
  .handler(async ({ context, data }) => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const { connectBroker } = await import("./connectors.server");
    const tenant = await ensurePersonalTenant(context.userId);
    const origin =
      data.origin ||
      process.env.BETTER_AUTH_URL ||
      process.env.APP_PUBLIC_URL ||
      "http://127.0.0.1:8080";
    return connectBroker({
      tenantId: tenant.id,
      userId: context.userId,
      broker: data.broker,
      origin,
    });
  });

export const disconnectBrokerFn = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((data: { broker: BrokerId }) => data)
  .handler(async ({ context, data }) => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const { disconnectBroker } = await import("./connectors.server");
    const tenant = await ensurePersonalTenant(context.userId);
    await disconnectBroker({ tenantId: tenant.id, broker: data.broker });
    return { ok: true };
  });

export const syncBrokersFn = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator((data: { broker?: BrokerId } | undefined) => data ?? {})
  .handler(async ({ context, data }) => {
    const { ensurePersonalTenant } = await import("./tenant.server");
    const { syncBrokers } = await import("./connectors.server");
    const tenant = await ensurePersonalTenant(context.userId);
    return syncBrokers(tenant.id, data.broker);
  });

export const saveSchwabAppCredentialsFn = createServerFn({ method: "POST" })
  .middleware([authMiddleware])
  .validator(
    (data: {
      clientId: string;
      clientSecret: string;
      redirectUri?: string;
      origin?: string;
    }) => data,
  )
  .handler(async ({ data }) => {
    const { saveSchwabAppCredentials } = await import(
      "./oauth/schwab.server"
    );
    const origin = (data.origin || "").replace(/\/$/, "");
    const redirectUri =
      data.redirectUri ||
      (origin ? `${origin}/api/v1/oauth/schwab/callback` : "");
    await saveSchwabAppCredentials({
      clientId: data.clientId,
      clientSecret: data.clientSecret,
      redirectUri,
    });
    return { ok: true };
  });
