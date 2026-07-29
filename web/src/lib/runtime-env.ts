/**
 * Process-level runtime probes (no secrets). Shared by db + auth status so we
 * never load PGLite on serverless.
 */

/**
 * PGLite is only viable in a long-lived Node process (Grok sandbox live preview
 * or local `npm run dev`). On Vercel/serverless the isolate dies after each
 * request, so a missing DATABASE_URL is a hard production failure.
 *
 * Important: the live-preview proxy sometimes forwards `Host` /
 * `x-forwarded-host` as the *published* `*.grok.me` name while the process is
 * still the sandbox. Host alone must not decide that PGLite is unusable.
 */
export function pgliteUsableInThisRuntime(): boolean {
  if (typeof process === "undefined") return false;
  if (process.env.VERCEL) return false;
  if (process.env.VERCEL_ENV) return false;
  if (process.env.AWS_LAMBDA_FUNCTION_NAME) return false;
  if (process.env.NETLIFY) return false;
  // Grok app-builder sandbox always has this marker and never sets VERCEL.
  if (process.env.GROK_AGENT || process.env.SANDBOX_SERVICE_ENV) return true;
  // Local / unknown long-lived Node — allow PGLite.
  return true;
}
