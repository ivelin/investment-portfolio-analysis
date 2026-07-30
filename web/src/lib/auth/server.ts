/**
 * Self-hosted Better Auth for THIS app (server-only).
 *
 * Sign-in (product path on Vercel):
 *   Better Auth **socialProviders** for Google + X (Twitter) using env
 *   `GOOGLE_CLIENT_ID/SECRET` and `TWITTER_CLIENT_ID/SECRET`. Sessions live on
 *   this origin at `/api/auth/*`. Email/password stays off.
 *
 * Legacy Grok broker (non-Vercel only):
 *   genericOAuth → auth.grok.me when not on Vercel and direct social env is
 *   absent (local / Grok sandbox). Never used as a Vercel fallback.
 *
 * NEVER import this from client code. Client: `@/lib/auth/client`.
 */
import { betterAuth } from "better-auth";
import { bearer, genericOAuth } from "better-auth/plugins";
import { tanstackStartCookies } from "better-auth/tanstack-start";
import { getCookie } from "@tanstack/react-start/server";
import { randomBytes } from "node:crypto";
import { dbSource, ensureDbReady, getPgPool, getPglite } from "../db";
import { resolveDatabaseUrl } from "../db-url";
import { pgliteUsableInThisRuntime } from "../runtime-env";
import { emailAndPasswordEnabled } from "./email-password";
import { SOCIAL_PROVIDERS } from "./providers";
import { pgliteDialect } from "./pglite-dialect";
import {
  GROK_ISSUER_DEFAULT,
  PREVIEW_ALLOWED_HOSTS,
  PREVIEW_CLIENT_ID,
  PREVIEW_CLIENT_SECRET,
} from "./preview";
import {
  buildSocialProvidersFromEnv,
  isAuthConfigured,
  resolveAuthBackendMode,
} from "./social-config";

void ensureDbReady();

const globalAuthRef = globalThis as typeof globalThis & {
  __grokAuthPreviewSecret__?: string;
  __grokAuthReady__?: Promise<void>;
};
function previewAuthSecret(): string {
  globalAuthRef.__grokAuthPreviewSecret__ ??= randomBytes(32).toString("hex");
  return globalAuthRef.__grokAuthPreviewSecret__;
}

const env = (key: string): string | undefined => {
  const value = process.env[key]?.trim();
  return value ? value : undefined;
};

const authDisabled = env("VITE_AUTH_ENABLED") === "false";
const backendMode = resolveAuthBackendMode(process.env);

/** True when real sign-in is available (direct social or non-Vercel Grok broker). */
export const authConfigured = !authDisabled && isAuthConfigured(process.env);

export const authBackendMode = backendMode;

// ── base URL / origins ─────────────────────────────────────────────────────
const vercelPublicUrl = env("VERCEL_URL")
  ? `https://${env("VERCEL_URL")}`
  : undefined;
const explicitBaseURL =
  env("BETTER_AUTH_URL") ?? env("APP_PUBLIC_URL") ?? vercelPublicUrl;
const previewAllowedHosts: string[] = [...PREVIEW_ALLOWED_HOSTS];
const LOCAL_DEV_ORIGINS: string[] = [
  "http://localhost:8080",
  "http://127.0.0.1:8080",
  "http://[::1]:8080",
];
const DYNAMIC_ALLOWED_HOSTS: string[] = [
  ...previewAllowedHosts,
  "localhost",
  "127.0.0.1",
  "[::1]",
  "*.grok.me",
  "*.vercel.app",
];
const baseURL = explicitBaseURL ?? {
  allowedHosts: DYNAMIC_ALLOWED_HOSTS,
  protocol: "auto" as const,
  fallback: "http://localhost:8080",
};

const trustedOrigins: string[] = [
  ...(explicitBaseURL ? [explicitBaseURL] : []),
  ...LOCAL_DEV_ORIGINS,
  "https://*.grok.me",
  "https://*.vercel.app",
  ...previewAllowedHosts,
  "*.grok.me",
  "*.vercel.app",
  ...previewAllowedHosts.flatMap((host) => [
    `https://${host}`,
    `http://${host}`,
  ]),
];

const databaseUrl = resolveDatabaseUrl();

// ── database handle (Neon pool / PGLite / fail closed) ─────────────────────
function createAuthDatabase():
  | import("pg").Pool
  | { dialect: ReturnType<typeof pgliteDialect>; type: "postgres" } {
  if (databaseUrl) {
    const target = { pool: null as import("pg").Pool | null };
    const resolve = async () => {
      target.pool ??= await getPgPool();
      return target.pool;
    };
    globalAuthRef.__grokAuthReady__ ??= resolve().then(() => undefined);

    const poolShape = {
      connect: async (...args: unknown[]) => {
        const pool = await resolve();
        return (pool.connect as (...a: unknown[]) => unknown)(...args);
      },
      query: async (...args: unknown[]) => {
        const pool = await resolve();
        return (pool.query as (...a: unknown[]) => unknown)(...args);
      },
      end: async (...args: unknown[]) => {
        if (!target.pool) return;
        return target.pool.end(...(args as []));
      },
    } as unknown as import("pg").Pool;

    return new Proxy(poolShape, {
      get(t, prop, receiver) {
        if (prop === "then") return undefined;
        if (prop in poolShape) {
          return Reflect.get(poolShape, prop, receiver);
        }
        if (target.pool) {
          const value = Reflect.get(target.pool, prop, receiver);
          return typeof value === "function"
            ? value.bind(target.pool)
            : value;
        }
        return undefined;
      },
      has(t, prop) {
        if (prop === "connect" || prop === "query" || prop === "end") return true;
        if (target.pool) return Reflect.has(target.pool, prop);
        return Reflect.has(poolShape, prop);
      },
    });
  }

  if (!pgliteUsableInThisRuntime()) {
    const reject = async () => {
      throw new Error(
        "AUTH_NO_DATABASE: Published deploy has no DATABASE_URL. " +
          "Sign-in cannot persist sessions until the host injects Neon Postgres.",
      );
    };
    const stub = {
      connect: reject,
      query: reject,
      end: reject,
    } as unknown as import("pg").Pool;
    return new Proxy(stub, {
      get(t, prop) {
        if (prop === "then") return undefined;
        return Reflect.get(t, prop);
      },
      has(_t, prop) {
        return prop === "connect" || prop === "query" || prop === "end";
      },
    });
  }

  return { dialect: pgliteDialect(() => getPglite()), type: "postgres" as const };
}

const database = createAuthDatabase();

export const SESSION_TOKEN_COOKIE = "__Host-grok-auth.session_token";

// ── providers: direct social vs Grok broker ────────────────────────────────
const socialProviders = buildSocialProvidersFromEnv(process.env);

const grokOAuthPlugin =
  backendMode === "grok_broker" && authConfigured
    ? (() => {
        const grokIssuer = env("GROK_AUTH_ISSUER") ?? GROK_ISSUER_DEFAULT;
        const grokClientId =
          env("GROK_AUTH_CLIENT_ID") ?? PREVIEW_CLIENT_ID;
        const grokClientSecret =
          env("GROK_AUTH_CLIENT_SECRET") ?? PREVIEW_CLIENT_SECRET;
        const issuerBase = grokIssuer.replace(/\/+$/, "");
        return genericOAuth({
          config: SOCIAL_PROVIDERS.map(({ providerId, brokerIdp }) => ({
            // Use social ids so the same button keys work for both modes.
            providerId,
            clientId: grokClientId as string,
            clientSecret: grokClientSecret as string,
            authorizationUrl: `${issuerBase}/api/auth/oauth2/authorize`,
            tokenUrl: `${issuerBase}/api/auth/oauth2/token`,
            userInfoUrl: `${issuerBase}/api/auth/oauth2/userinfo`,
            scopes: ["openid", "profile", "email"],
            authorizationUrlParams: { idp: brokerIdp, prompt: "login" },
          })),
        });
      })()
    : null;

const trustedSocialIds = SOCIAL_PROVIDERS.map((p) => p.providerId);

export const auth = betterAuth({
  baseURL,
  secret: env("BETTER_AUTH_SECRET") ?? previewAuthSecret(),
  database,
  trustedOrigins,

  // Direct Google / X on Vercel (and any host with env). Empty object when
  // using Grok broker only — then genericOAuth supplies providers.
  socialProviders:
    backendMode === "direct_social" ? socialProviders : {},

  account: {
    encryptOAuthTokens: true,
    accountLinking: {
      enabled: true,
      trustedProviders: trustedSocialIds,
      requireLocalEmailVerified: false,
    },
  },

  session: { cookieCache: { enabled: true, maxAge: 300 } },

  ...(emailAndPasswordEnabled ? { emailAndPassword: { enabled: true } } : {}),

  advanced: {
    useSecureCookies: false,
    defaultCookieAttributes: { secure: true, sameSite: "lax", path: "/" },
    cookies: {
      session_token: { name: SESSION_TOKEN_COOKIE },
      session_data: { name: "__Host-grok-auth.session_data" },
      account_data: { name: "__Host-grok-auth.account_data" },
      dont_remember: { name: "__Host-grok-auth.dont_remember" },
    },
  },

  plugins: [
    ...(grokOAuthPlugin ? [grokOAuthPlugin] : []),
    bearer(),
    tanstackStartCookies(),
  ],
});

export function ensureAuthReady(): Promise<void> {
  return ensureDbReady().then(() => {
    if (dbSource === "neon" && globalAuthRef.__grokAuthReady__) {
      return globalAuthRef.__grokAuthReady__;
    }
    if (!databaseUrl && !pgliteUsableInThisRuntime()) {
      return Promise.reject(
        new Error(
          "AUTH_NO_DATABASE: Published deploy has no DATABASE_URL. " +
            "Sign-in cannot persist sessions until the host injects Neon Postgres.",
        ),
      );
    }
  });
}

export function readSessionToken(): string | null {
  return getCookie(SESSION_TOKEN_COOKIE) ?? null;
}

export { SOCIAL_PROVIDERS, GROK_PROVIDERS } from "./providers";
