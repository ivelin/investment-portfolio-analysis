#!/usr/bin/env node
/**
 * MCP critical path — drives shipped mcpGetHandler / mcpPostHandler / runTool.
 * Catalog + workspace_summary + list_accounts + positions; fail closed; no secrets.
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

const EXPECTED_TOOLS = [
  "list_tools",
  "workspace_summary",
  "list_accounts",
  "positions",
  "fund_series",
  "list_connectors",
];

try {
  const { mcpGetHandler, mcpPostHandler, TOOL_CATALOG, runTool } = await load(
    "/src/routes/api/v1/mcp.ts",
  );

  // --- GET catalog (no auth) ---
  {
    const res = await mcpGetHandler();
    assertStatus(res, 200, "mcp get");
    const body = await res.json();
    assert(body.ok === true && body.mode === "multi-tenant", "mcp catalog meta");
    const names = (body.tools || []).map((t) => t.name);
    for (const n of EXPECTED_TOOLS) {
      assert(names.includes(n), `catalog missing ${n}`);
    }
    assert(
      TOOL_CATALOG.length === EXPECTED_TOOLS.length,
      "TOOL_CATALOG length",
    );
  }

  // --- POST without auth ---
  {
    const res = await mcpPostHandler({
      request: new Request("http://localhost/api/v1/mcp", {
        method: "POST",
        body: JSON.stringify({ tool: "list_tools" }),
        headers: { "content-type": "application/json" },
      }),
    });
    assert(res.status === 401, `mcp unauth ${res.status}`);
  }

  // --- POST invalid JSON ---
  {
    const { rawKey } = await createTenantWithApiKey("mcp-json-user", "write");
    const res = await mcpPostHandler({
      request: authRequest("http://localhost/api/v1/mcp", rawKey, {
        method: "POST",
        body: "not-json",
        headers: { "content-type": "application/json" },
      }),
    });
    assertStatus(res, 400, "mcp bad json");
  }

  // --- authenticated tools ---
  {
    const { tenant, rawKey } = await createTenantWithApiKey(
      "mcp-tools-user",
      "write",
    );

    async function postTool(tool, args) {
      const res = await mcpPostHandler({
        request: authRequest("http://localhost/api/v1/mcp", rawKey, {
          method: "POST",
          body: JSON.stringify({ tool, args }),
        }),
      });
      return { res, body: await res.json() };
    }

    {
      const { res, body } = await postTool("list_tools");
      assertStatus(res, 200, "list_tools");
      assert(body.ok && body.tool === "list_tools", "list_tools body");
      const names = body.result.tools.map((t) => t.name);
      for (const n of EXPECTED_TOOLS) assert(names.includes(n), n);
      assertNoSecrets(body, "list_tools");
    }

    {
      const { res, body } = await postTool("workspace_summary");
      assertStatus(res, 200, "workspace_summary");
      assert(body.ok && body.result, "workspace_summary result");
      assert(
        body.result.id === tenant.id || body.result.name,
        "workspace scoped",
      );
      assertNoSecrets(body, "workspace_summary");
    }

    let accountId = null;
    {
      const { res, body } = await postTool("list_accounts");
      assertStatus(res, 200, "list_accounts");
      assert(Array.isArray(body.result.accounts), "accounts array");
      assert(body.result.accounts.length >= 1, "has demo account");
      accountId = body.result.accounts[0].id;
      assert(
        body.result.accounts.every((a) => typeof a.accountMask === "string"),
        "masks only",
      );
      assertNoSecrets(body, "list_accounts");
    }

    {
      const { res, body } = await postTool("positions", { accountId });
      assertStatus(res, 200, "positions");
      assert(body.result.accountId === accountId, "positions account");
      assert(Array.isArray(body.result.positions), "positions array");
      assert(body.result.positions.length >= 1, "demo positions");
      assertNoSecrets(body, "positions");
    }

    {
      const { res, body } = await postTool("fund_series", {
        accountId,
        limit: 10,
      });
      assertStatus(res, 200, "fund_series");
      assert(Array.isArray(body.result.series), "series array");
      assert(body.result.series.length >= 1, "series points");
      assertNoSecrets(body, "fund_series");
    }

    {
      const { res, body } = await postTool("list_connectors");
      assertStatus(res, 200, "list_connectors");
      assert(Array.isArray(body.result.connectors), "connectors");
      assertNoSecrets(body, "list_connectors");
    }

    {
      const { res, body } = await postTool("not_a_real_tool");
      assertStatus(res, 200, "unknown tool");
      assert(body.result.error, "unknown tool error");
      assert(Array.isArray(body.result.tools), "lists tools on error");
    }

    // runTool directly (same shipped function) for tenant isolation sanity
    {
      const { tenant: other } = await createTenantWithApiKey(
        "mcp-other-user",
        "read",
      );
      const leak = await runTool("positions", other.id, {
        accountId, // foreign account id
      });
      assert(
        leak.positions?.length === 0 || leak.accountId == null,
        "foreign account positions empty",
      );
    }
  }

  console.log("OK mcp critical-path tests passed");
} catch (err) {
  console.error("FAIL", err);
  process.exitCode = 1;
} finally {
  await closeHarness();
}
