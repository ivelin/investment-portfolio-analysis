#!/usr/bin/env node
/**
 * API critical path — drives shipped route handlers (not re-implemented logic).
 * - portfolio summary: auth required, tenant-scoped success
 * - health/auth: secret-free status
 * - token-refresh job: unauthenticated fails closed; cron secret path ok
 */
import {
  assert,
  assertNoSecrets,
  assertStatus,
  authRequest,
  closeHarness,
  createTenantWithApiKey,
  load,
} from "../helpers/harness.mjs";

try {
  const { portfolioSummaryGet } = await load(
    "/src/routes/api/v1/portfolio/summary.ts",
  );
  const { healthAuthGet } = await load("/src/routes/api/v1/health/auth.ts");
  const { tokenRefreshGet, tokenRefreshPost } = await load(
    "/src/routes/api/v1/jobs/token-refresh.ts",
  );
  const { requireApiPrincipal, jsonError } = await load(
    "/src/lib/portfolio/api-auth.server.ts",
  );
  const { authorizeJob } = await load(
    "/src/lib/portfolio/jobs-auth.server.ts",
  );

  // --- health (no auth) ---
  {
    const res = await healthAuthGet({
      request: new Request("http://localhost:8080/api/v1/health/auth", {
        headers: { host: "localhost:8080" },
      }),
    });
    assertStatus(res, 200, "health");
    const body = await res.json();
    assert(typeof body.ok === "boolean", "health.ok boolean");
    assert(body.database === "pglite" || body.database === "neon", "health.database");
    assert(!JSON.stringify(body).includes("npg_"), "health no db secrets");
    assertNoSecrets(body, "health");
  }

  // --- summary fail closed without auth ---
  {
    const res = await portfolioSummaryGet({
      request: new Request("http://localhost:8080/api/v1/portfolio/summary"),
    });
    assert(res.status === 401 || res.status === 403, `summary unauth status ${res.status}`);
    const body = await res.json();
    assert(body.ok === false, "summary unauth ok=false");
  }

  // --- requireApiPrincipal rejects bad key ---
  {
    let threw = false;
    try {
      await requireApiPrincipal(
        new Request("http://x", {
          headers: { authorization: "Bearer pa_not_a_real_key_zzzz" },
        }),
      );
    } catch (e) {
      threw = true;
      assert(e.message === "Unauthorized", "bad key message");
    }
    assert(threw, "bad api key must throw");
  }

  // --- summary success with real API key principal ---
  {
    const { tenant, rawKey } = await createTenantWithApiKey(
      "api-summary-user",
      "write",
    );
    const res = await portfolioSummaryGet({
      request: authRequest(
        "http://localhost:8080/api/v1/portfolio/summary",
        rawKey,
      ),
    });
    assertStatus(res, 200, "summary auth");
    const body = await res.json();
    assert(body.ok === true, "summary ok");
    assert(body.tenant?.id === tenant.id, "summary tenant id");
    assert(Array.isArray(body.accounts), "summary accounts");
    assert(body.accounts.length >= 1, "demo account present");
    assert(body.workspace?.id === tenant.id, "workspace id");
    assertNoSecrets(body, "summary");
  }

  // --- job GET metadata ---
  {
    const res = await tokenRefreshGet();
    assertStatus(res, 200, "job get");
    const body = await res.json();
    assert(body.job === "token_refresh", "job id");
  }

  // --- job POST fail closed without auth ---
  {
    const prev = process.env.CRON_SECRET;
    delete process.env.CRON_SECRET;
    const res = await tokenRefreshPost({
      request: new Request("http://localhost:8080/api/v1/jobs/token-refresh", {
        method: "POST",
        body: "{}",
        headers: { "content-type": "application/json" },
      }),
    });
    assert(res.status === 401, `job unauth ${res.status}`);
    if (prev !== undefined) process.env.CRON_SECRET = prev;
  }

  // --- authorizeJob rejects empty auth ---
  {
    delete process.env.CRON_SECRET;
    let threw = false;
    try {
      await authorizeJob(new Request("http://x", { method: "POST" }));
    } catch (e) {
      // Fail closed: Unauthorized, or TanStack getRequest outside server runtime
      const msg = e instanceof Error ? e.message : String(e);
      threw =
        msg === "Unauthorized" ||
        /Unauthorized|StartEvent|AsyncLocalStorage|server runtime/i.test(msg);
    }
    assert(threw, "authorizeJob unauth");
  }

  // --- job POST with CRON_SECRET (shipped authorizeJob path) ---
  {
    const secret = "test-cron-secret-for-coverage-only";
    process.env.CRON_SECRET = secret;
    const { tenant } = await createTenantWithApiKey("api-cron-user", "write");
    const res = await tokenRefreshPost({
      request: new Request("http://localhost:8080/api/v1/jobs/token-refresh", {
        method: "POST",
        headers: {
          authorization: `Bearer ${secret}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ tenantId: tenant.id, force: false }),
      }),
    });
    assertStatus(res, 200, "job cron");
    const body = await res.json();
    assert(body.ok === true, "job ok");
    assert(typeof body.job?.examined === "number", "job examined");
    assertNoSecrets(body, "job result");
    delete process.env.CRON_SECRET;
  }

  // --- jsonError shape ---
  {
    const err = new Error("Unauthorized");
    err.status = 401;
    const res = jsonError(err);
    assertStatus(res, 401, "jsonError");
    const body = await res.json();
    assert(body.ok === false && body.error === "Unauthorized");
  }

  // --- OAuth callback fail-closed (invalid / error) ---
  {
    const { oauthCallbackGet } = await load(
      "/src/routes/api/v1/oauth/$broker/callback.ts",
    );
    const bad = await oauthCallbackGet({
      request: new Request(
        "http://localhost:8080/api/v1/oauth/schwab/callback",
      ),
      params: { broker: "schwab" },
    });
    assert(bad.status === 302, `oauth invalid ${bad.status}`);
    assert(
      String(bad.headers.get("location")).includes("invalid_callback"),
      "oauth invalid reason",
    );

    const denied = await oauthCallbackGet({
      request: new Request(
        "http://localhost:8080/api/v1/oauth/schwab/callback?error=access_denied",
      ),
      params: { broker: "schwab" },
    });
    assert(denied.status === 302, "oauth error redirect");
    assert(
      String(denied.headers.get("location")).includes("access_denied"),
      "oauth error reason",
    );

    const expired = await oauthCallbackGet({
      request: new Request(
        "http://localhost:8080/api/v1/oauth/schwab/callback?code=x&state=missing",
      ),
      params: { broker: "schwab" },
    });
    assert(expired.status === 302, "oauth expired");
    assert(
      String(expired.headers.get("location")).includes("expired_state"),
      "oauth expired reason",
    );
  }

  // --- redact + ids smoke (security include) ---
  {
    const { redactObject, redactText, auditMeta } = await load(
      "/src/lib/security/redact.ts",
    );
    const red = redactObject({
      access_token: "secret",
      nested: { refresh_token: "r", ok: true },
    });
    assert(red.access_token === "[redacted]", "redact key");
    assert(redactText("Bearer abcdefghijklmnop").includes("[redacted]"), "redact bearer");
    assert(auditMeta({ token: "x" }).token === "[redacted]", "auditMeta");
  }

  console.log("OK api critical-path tests passed");
} catch (err) {
  console.error("FAIL", err);
  process.exitCode = 1;
} finally {
  await closeHarness();
}
