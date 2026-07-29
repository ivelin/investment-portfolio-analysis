import { createServerFn } from "@tanstack/react-start";
import { getRequest } from "@tanstack/react-start/server";
import type { AuthRuntimeStatus } from "./auth-runtime-status";

export const getAuthStatusFn = createServerFn({ method: "GET" }).handler(
  async (): Promise<AuthRuntimeStatus> => {
    const { getAuthRuntimeStatus } = await import("./auth-runtime-status");
    let host: string | null = null;
    try {
      const req = getRequest();
      host =
        req.headers.get("x-forwarded-host") ||
        req.headers.get("host") ||
        null;
    } catch {
      host = null;
    }
    return getAuthRuntimeStatus(host);
  },
);
