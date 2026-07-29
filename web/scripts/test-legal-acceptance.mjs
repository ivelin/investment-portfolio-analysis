#!/usr/bin/env node
import { createViteTestServer } from "./vite-test-server.mjs";
import assert from "node:assert/strict";

const vite = await createViteTestServer();

try {
  const docs = await vite.ssrLoadModule("/src/lib/compliance/legal-docs.ts");
  const { ensureDbReady } = await vite.ssrLoadModule("/src/lib/db.ts");
  const { getLegalStatus, recordLegalAcceptance } = await vite.ssrLoadModule(
    "/src/lib/compliance/legal.server.ts",
  );

  assert.ok(docs.LEGAL_PACK_VERSION);
  assert.ok(docs.TERMS_SECTIONS.length >= 6);
  assert.ok(docs.PRIVACY_SECTIONS.length >= 6);
  assert.ok(/not investment advice/i.test(docs.ACCEPT_SUMMARY));
  assert.ok(docs.MARKET_RISK_LINE.length > 20);
  // product language in accept summary — not stack jargon
  assert.ok(!/pkce|oauth|tenant_id/i.test(docs.ACCEPT_SUMMARY));

  await ensureDbReady();
  const userId = "legal-test-user";
  let status = await getLegalStatus(userId);
  assert.equal(status.accepted, false);
  assert.equal(status.requiredVersion, docs.LEGAL_PACK_VERSION);

  status = await recordLegalAcceptance({ userId, tenantId: null });
  assert.equal(status.accepted, true);
  assert.ok(status.acceptedAt);

  // idempotent
  const again = await recordLegalAcceptance({ userId, tenantId: null });
  assert.equal(again.accepted, true);

  console.log("OK legal acceptance tests passed");
} catch (e) {
  console.error("FAIL", e);
  process.exitCode = 1;
} finally {
  await vite.close();
}
