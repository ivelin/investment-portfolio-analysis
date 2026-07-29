#!/usr/bin/env node
/**
 * Broker setup path: Schwab app credentials → configured → OAuth start isolation.
 * No real Schwab network calls; mocks authorize URL builder path via sealed creds.
 */
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

// Avoid accidental env short-circuit during this process
delete process.env.SCHWAB_CLIENT_ID;
delete process.env.SCHWAB_CLIENT_SECRET;

try {
  const { ensureDbReady, getSql } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { ensurePersonalTenant } = await vite.ssrLoadModule(
    "/src/lib/portfolio/tenant.server.ts",
  );
  const {
    saveSchwabAppCredentials,
    resolveSchwabAppCredentials,
    schwabOAuthConfigured,
    buildSchwabAuthorizeUrl,
  } = await vite.ssrLoadModule("/src/lib/portfolio/oauth/schwab.server.ts");
  const { listConnectors, connectBroker } = await vite.ssrLoadModule(
    "/src/lib/portfolio/connectors.server.ts",
  );
  const { sealConnectorSecret, openConnectorSecret } = await vite.ssrLoadModule(
    "/src/lib/portfolio/oauth/secrets.server.ts",
  );
  const { newId } = await vite.ssrLoadModule("/src/lib/security/ids.ts");
  const {
    classifyConnectorUiStatus,
    primaryConnectCta,
  } = await vite.ssrLoadModule("/src/lib/portfolio/connector-status.ts");

  await ensureDbReady();
  const sql = await getSql();

  // Clean platform schwab row from prior runs
  await sql`delete from platform_oauth_clients where broker = ${"schwab"}`;

  assert.equal(await schwabOAuthConfigured(), false, "start unconfigured");

  const tA = await ensurePersonalTenant("setup-user-a");
  const tB = await ensurePersonalTenant("setup-user-b");
  assert.notEqual(tA.id, tB.id);

  let listA = await listConnectors(tA.id);
  const schwabCard = listA.find((c) => c.broker === "schwab");
  assert.ok(schwabCard);
  assert.equal(schwabCard.oauthConfigured, false);
  assert.equal(
    primaryConnectCta({
      status: schwabCard.status,
      oauthConfigured: schwabCard.oauthConfigured,
    }),
    "how_to_connect",
  );
  assert.equal(
    classifyConnectorUiStatus({
      status: schwabCard.status,
      oauthConfigured: false,
    }),
    "setup_needed",
  );

  // Before credentials: connect returns not_configured (path to setup)
  const blocked = await connectBroker({
    tenantId: tA.id,
    userId: "setup-user-a",
    broker: "schwab",
    origin: "https://app.example.com",
  });
  assert.equal(blocked.kind, "not_configured");

  const redirectUri = "https://app.example.com/api/v1/oauth/schwab/callback";
  await saveSchwabAppCredentials({
    clientId: "test-schwab-client-id",
    clientSecret: "test-schwab-client-secret",
    redirectUri,
  });

  assert.equal(await schwabOAuthConfigured(), true);
  const creds = await resolveSchwabAppCredentials();
  assert.equal(creds?.clientId, "test-schwab-client-id");
  assert.equal(creds?.clientSecret, "test-schwab-client-secret");

  // Credentials are platform-level (not copied into tenant A secrets as user tokens)
  listA = await listConnectors(tA.id);
  assert.equal(
    listA.find((c) => c.broker === "schwab")?.oauthConfigured,
    true,
  );
  const listB = await listConnectors(tB.id);
  assert.equal(
    listB.find((c) => c.broker === "schwab")?.oauthConfigured,
    true,
    "app credentials enable all tenants to start OAuth",
  );

  // Authorize URL builds with PKCE state (no network)
  const built = await buildSchwabAuthorizeUrl({
    redirectUri,
    stateId: "oauth_teststate",
  });
  assert.ok(built.authorizeUrl.includes("client_id=test-schwab-client-id"));
  assert.ok(built.authorizeUrl.includes("code_challenge"));
  assert.ok(built.authorizeUrl.includes("state=oauth_teststate"));
  assert.ok(built.codeVerifier.length > 20);

  // After configure: connect starts OAuth (writes state under tenant only)
  const started = await connectBroker({
    tenantId: tA.id,
    userId: "setup-user-a",
    broker: "schwab",
    origin: "https://app.example.com",
  });
  assert.equal(started.kind, "oauth_redirect");
  assert.ok(started.authorizeUrl.includes("schwabapi.com") || started.authorizeUrl.includes("client_id="));

  const statesA = await sql`
    select tenant_id, broker from broker_oauth_states where tenant_id = ${tA.id}
  `;
  const statesB = await sql`
    select tenant_id from broker_oauth_states where tenant_id = ${tB.id}
  `;
  assert.ok(statesA.length >= 1, "tenant A has oauth state");
  assert.equal(statesB.length, 0, "tenant B has no oauth state from A");

  // Simulate sealed user tokens only for A — B must not see them
  const connA = (
    await sql`select id from connectors where tenant_id = ${tA.id} and broker = ${"schwab"}`
  )[0];
  assert.ok(connA);
  const userTokens = {
    kind: "direct_oauth",
    broker: "schwab",
    access_token: "user-a-access-ONLY",
    refresh_token: "user-a-refresh-ONLY",
    expires_at: Date.now() + 3600_000,
    obtainedAt: new Date().toISOString(),
  };
  await sql`
    insert into connector_secrets (connector_id, tenant_id, ciphertext, key_version)
    values (${connA.id}, ${tA.id}, ${sealConnectorSecret(userTokens)}, ${1})
    on conflict (connector_id) do update set
      ciphertext = excluded.ciphertext,
      tenant_id = ${tA.id}
  `;
  await sql`
    update connectors set status = ${"connected"} where id = ${connA.id} and tenant_id = ${tA.id}
  `;

  const secretsB = await sql`
    select s.ciphertext from connector_secrets s
    join connectors c on c.id = s.connector_id
    where c.tenant_id = ${tB.id} and c.broker = ${"schwab"}
  `;
  assert.equal(secretsB.length, 0, "tenant B has no user tokens");

  const secretsA = await sql`
    select ciphertext from connector_secrets
    where tenant_id = ${tA.id} and connector_id = ${connA.id}
  `;
  const opened = openConnectorSecret(secretsA[0].ciphertext);
  assert.equal(opened.access_token, "user-a-access-ONLY");

  // Redaction: platform client secret must not appear in listConnectors output
  const publicJson = JSON.stringify(await listConnectors(tA.id));
  assert.ok(!publicJson.includes("test-schwab-client-secret"));
  assert.ok(!publicJson.includes("user-a-access-ONLY"));

  console.log("OK broker setup path tests passed");
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close();
}
