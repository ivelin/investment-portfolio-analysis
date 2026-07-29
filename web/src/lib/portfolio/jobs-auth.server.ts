import { getSessionUser } from "@/lib/auth/verify.server";
import { ensurePersonalTenant } from "./tenant.server";

export type JobPrincipal =
  | { auth: "cron"; tenantId?: undefined }
  | { auth: "session"; userId: string; tenantId: string };

export async function authorizeJob(request: Request): Promise<JobPrincipal> {
  const auth = request.headers.get("authorization") || "";
  const cron = process.env.CRON_SECRET?.trim();
  if (cron && auth === `Bearer ${cron}`) {
    return { auth: "cron" };
  }
  const user = await getSessionUser();
  if (!user) {
    const err = new Error("Unauthorized");
    (err as Error & { status?: number }).status = 401;
    throw err;
  }
  const tenant = await ensurePersonalTenant(user.id);
  return { auth: "session", userId: user.id, tenantId: tenant.id };
}
