/**
 * Self-hosted Better Auth for THIS app (server-only).
 *
 * Sign-in paths:
 *   1. **Direct social** (Vercel / any host with GOOGLE_* / TWITTER_*):
 *      Better Auth socialProviders → Google / X.
 *   2. **Grok broker** (sandbox preview, Grok CLI, Grok *.grok.me publish):
 *      genericOAuth → auth.grok.me. Preview client accepts
 *      `https://*.grok-sandbox.com/api/auth/oauth2/callback/*`.
 *      Deployed grok.me uses injected GROK_AUTH_* client — platform must
 *      register exact redirect URIs for
 *      `/api/auth/oauth2/callback/{google,twitter}` on the app origin.
 *
 * Email/password stays off. NEVER import from client code.
 */
import { betterAuth } from "better-auth";
import { createAuthMiddleware } from "better-auth/api";
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
  appOAuthCallbackUrl,
  fixOAuthAuthorizeUrl,
  originFromAuthBaseURL,
} from "./oauth-redirect";
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

/** True when real sign-in is available (direct social or Grok broker). */
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
  "localhost:8080",
  "127.0.0.1",
  "127.0.0.1:8080",
  "[::1]",
  "[::1]:8080",
  "*.grok.me",
  "*.vercel.app",
  "*.grok-sandbox.com",
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
  "https://*.grok-sandbox.com",
  ...previewAllowedHosts,
  "*.grok.me",
  "*.vercel.app",
  "*.grok-sandbox.com",
  ...previewAllowedHosts.flatMap((host) => [
    `https://${host}`,
    `http://${host}`,
  ]),
];

/** Public origin for absolute OAuth callbacks (never includes /api/auth path). */
function publicAppOrigin(): string | undefined {
  if (explicitBaseURL) {
    try {
      return new URL(explicitBaseURL).origin;
    } catch {
      /* fall through */
    }
  }
  return undefined;
}

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
        if (prop === "connect" || prop === "query" || prop === "end")
          return true;
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

  return {
    dialect: pgliteDialect(() => getPglite()),
    type: "postgres" as const,
  };
}

const database = createAuthDatabase();

export const SESSION_TOKEN_COOKIE = "__Host-grok-auth.session_token";

// ── providers: direct social vs Grok broker ────────────────────────────────
const socialProviders = buildSocialProvidersFromEnv(process.env);

const appOriginForCallbacks = publicAppOrigin();

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
            providerId,
            clientId: grokClientId as string,
            clientSecret: grokClientSecret as string,
            authorizationUrl: `${issuerBase}/api/auth/oauth2/authorize`,
            tokenUrl: `${issuerBase}/api/auth/oauth2/token`,
            userInfoUrl: `${issuerBase}/api/auth/oauth2/userinfo`,
            scopes: ["openid", "profile", "email"],
            // Explicit absolute callback when public origin known (publish).
            // Platform GROK_AUTH client must register these exact URIs.
            ...(appOriginForCallbacks
              ? {
                  redirectURI: appOAuthCallbackUrl(
                    appOriginForCallbacks,
                    providerId,
                  ),
                }
              : {}),
            authorizationUrlParams: {
              idp: brokerIdp,
              prompt: "login",
            },
          })),
        });
      })()
    : null;

/**
 * After sign-in/oauth2 (and social), rewrite authorize URL:
 * absolute redirect_uri + broker idp + prompt.
 */
const absoluteOAuthRedirectPlugin = {
  id: "absolute-oauth-redirect-uri",
  hooks: {
    after: [
      {
        matcher(ctx: { path?: string }) {
          const p = ctx.path ?? "";
          return (
            p === "/sign-in/oauth2" ||
            p === "/sign-in/social" ||
            p.startsWith("/sign-in/oauth2") ||
            p.startsWith("/sign-in/social")
          );
        },
        handler: createAuthMiddleware(async (ctx) => {
          const returned = ctx.context.returned as
            | { url?: string }
            | undefined
            | null;
          if (!returned || typeof returned !== "object") return;
          if (typeof returned.url !== "string") return;
          const origin =
            originFromAuthBaseURL(ctx.context.baseURL) ||
            appOriginForCallbacks ||
            null;
          if (!origin) return;
          const body = ctx.body as { providerId?: string } | undefined;
          const fixed = fixOAuthAuthorizeUrl(returned.url, origin, {
            providerId: body?.providerId,
          });
          if (fixed !== returned.url) {
            returned.url = fixed;
          }
        }),
      },
    ],
  },
};

const trustedSocialIds = SOCIAL_PROVIDERS.map((p) => p.providerId);

export const auth = betterAuth({
  baseURL,
  secret: env("BETTER_AUTH_SECRET") ?? previewAuthSecret(),
  database,
  trustedOrigins,

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
    trustedProxyHeaders: true,
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
    absoluteOAuthRedirectPlugin,
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
