#!/usr/bin/env node
/**
 * Broker connectors are read-only analysis only.
 * - Policy unit tests (allow / deny matrices)
 * - Static scan of src/ for write/trade symbols and bare broker fetch
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { createViteTestServer } from "./vite-test-server.mjs";

const root = join(import.meta.dirname, "..");
const vite = await createViteTestServer();

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (
      name === "node_modules" ||
      name === ".git" ||
      name === "dist" ||
      name === ".vercel" ||
      name === "coverage"
    ) {
      continue;
    }
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx|mjs|js)$/.test(name)) out.push(p);
  }
  return out;
}

try {
  const policy = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/read-only-policy.ts",
  );
  const http = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/broker-http.ts",
  );
  const catalog = await vite.ssrLoadModule(
    "/src/lib/portfolio/brokers/catalog.ts",
  );
  const intended = await vite.ssrLoadModule(
    "/src/lib/compliance/intended-use.ts",
  );

  // ── Product flags ─────────────────────────────────────────────────────
  assert.equal(policy.BROKER_CONNECTOR_MODE, "read_only_analysis");
  assert.equal(intended.PRODUCT_INTENDED_USE.placesOrders, false);
  assert.equal(intended.PRODUCT_INTENDED_USE.previewsOrders, false);
  assert.equal(intended.PRODUCT_INTENDED_USE.transfersFunds, false);
  assert.equal(
    intended.PRODUCT_INTENDED_USE.brokerAccessMode,
    "read_only_analysis",
  );

  for (const id of catalog.BROKER_IDS) {
    const def = catalog.BROKERS[id];
    assert.equal(
      def.accessMode,
      "read_only_analysis",
      `${id} must be read_only_analysis`,
    );
    assert.ok(
      !def.capabilities?.includes?.("trade"),
      `${id} must not list trade capability`,
    );
  }

  // ── Allow matrix ──────────────────────────────────────────────────────
  const allow = [
    {
      url: "https://api.schwabapi.com/trader/v1/accounts/accountNumbers",
      method: "GET",
      purpose: "portfolio_read",
    },
    {
      url: "https://api.schwabapi.com/trader/v1/accounts/HASH?fields=positions",
      method: "GET",
      purpose: "portfolio_read",
    },
    {
      url: "https://api.schwabapi.com/v1/oauth/token",
      method: "POST",
      purpose: "oauth_token",
    },
    {
      url: "https://api.robinhood.com/oauth2/token/",
      method: "POST",
      purpose: "oauth_token",
    },
    {
      url: "https://agent.robinhood.com/.well-known/oauth-authorization-server",
      method: "GET",
      purpose: "oauth_discovery",
    },
    {
      url: "https://agent.robinhood.com/oauth/trading/register",
      method: "POST",
      purpose: "oauth_registration",
    },
  ];
  for (const c of allow) {
    assert.doesNotThrow(
      () =>
        http.assertBrokerFetchWouldAllow(c.url, {
          method: c.method,
          purpose: c.purpose,
        }),
      `should allow ${c.method} ${c.url}`,
    );
  }

  // ── Deny matrix ───────────────────────────────────────────────────────
  const deny = [
    {
      url: "https://api.schwabapi.com/trader/v1/accounts/HASH/orders",
      method: "POST",
      purpose: "portfolio_read",
    },
    {
      url: "https://api.schwabapi.com/trader/v1/orders",
      method: "GET",
      purpose: "portfolio_read",
    },
    {
      url: "https://api.schwabapi.com/trader/v1/accounts/HASH/orders",
      method: "GET",
      purpose: "portfolio_read",
    },
    {
      url: "https://api.schwabapi.com/trader/v1/accounts/HASH",
      method: "POST",
      purpose: "portfolio_read",
    },
    {
      url: "https://api.schwabapi.com/trader/v1/transfer",
      method: "POST",
      purpose: "oauth_token",
    },
    {
      url: "https://api.robinhood.com/orders/",
      method: "POST",
      purpose: "portfolio_read",
    },
    {
      url: "https://api.schwabapi.com/trader/v1/accounts/HASH/orders/preview",
      method: "POST",
      purpose: "portfolio_read",
    },
  ];
  for (const c of deny) {
    assert.throws(
      () =>
        http.assertBrokerFetchWouldAllow(c.url, {
          method: c.method,
          purpose: c.purpose,
        }),
      (err) =>
        err &&
        (err.code === "BROKER_WRITE_FORBIDDEN" ||
          err.name === "BrokerWriteForbiddenError"),
      `should deny ${c.method} ${c.url}`,
    );
  }

  // ── MCP tool names ────────────────────────────────────────────────────
  const badTools = [
    "place_order",
    "place_equity_order",
    "place_previewed_order",
    "cancel_order",
    "submit_order",
    "preview_order",
    "execute_trade",
    "withdraw",
  ];
  for (const name of badTools) {
    assert.throws(
      () => policy.assertMcpToolReadOnly(name),
      (err) => err?.code === "BROKER_WRITE_FORBIDDEN",
      `tool ${name}`,
    );
  }
  assert.doesNotThrow(() => policy.assertMcpToolReadOnly("positions"));
  assert.doesNotThrow(() => policy.assertMcpToolReadOnly("workspace_summary"));
  assert.doesNotThrow(() => policy.assertMcpToolReadOnly("list_connectors"));

  // ── Static scan ───────────────────────────────────────────────────────
  const srcRoot = join(root, "src");
  const files = walk(srcRoot);
  const forbidRe =
    /\b(place_order|placeOrder|submit_order|submitOrder|create_order|preview_order|previewOrder|cancel_order|cancelOrder|replace_order|execute_trade|place_equity_order|place_option_order|place_previewed_order)\b/;

  const policyRel = "src/lib/portfolio/brokers/read-only-policy.ts";
  const testSelf = "scripts/test-broker-read-only.mjs";

  for (const file of files) {
    const rel = relative(root, file);
    const text = readFileSync(file, "utf8");
    if (rel === policyRel) continue;
    // Allow mentions in comments about the promise / docs strings only if not as identifiers?
    // Fail hard on symbol-like usage.
    const lines = text.split("\n");
    lines.forEach((line, i) => {
      if (forbidRe.test(line) && !line.trim().startsWith("//") && !line.trim().startsWith("*")) {
        // allow string lists in policy tests are outside src
        assert.fail(
          `Forbidden broker write symbol in ${rel}:${i + 1}: ${line.trim().slice(0, 120)}`,
        );
      }
    });
  }

  // Bare fetch to broker hosts outside broker-http / allowed modules
  const brokerHostRe =
    /fetch\s*\(\s*[`'"]https?:\/\/[^`'"]*(schwabapi\.com|api\.robinhood\.com|agent\.robinhood\.com|ibkr\.com)/;
  const allowFetchFiles = new Set([
    "src/lib/portfolio/brokers/broker-http.ts",
  ]);
  for (const file of files) {
    const rel = relative(root, file);
    if (allowFetchFiles.has(rel)) continue;
    const text = readFileSync(file, "utf8");
    if (brokerHostRe.test(text)) {
      assert.fail(
        `Bare fetch to broker host in ${rel} — use brokerFetch() from broker-http.ts`,
      );
    }
  }

  // Also scan for await fetch( variable patterns that might be broker - softer:
  // require no `await fetch(` in schwab.server, mcp-oauth, refresh (must be brokerFetch)
  for (const rel of [
    "src/lib/portfolio/oauth/schwab.server.ts",
    "src/lib/portfolio/oauth/mcp-oauth.server.ts",
    "src/lib/portfolio/oauth/refresh.server.ts",
  ]) {
    const text = readFileSync(join(root, rel), "utf8");
    assert.ok(
      !/\bawait\s+fetch\s*\(/.test(text),
      `${rel} must not call bare fetch; use brokerFetch`,
    );
    assert.ok(
      text.includes("brokerFetch"),
      `${rel} must import/use brokerFetch`,
    );
  }

  console.log("OK broker read-only policy tests passed");
} finally {
  await vite.close();
}
