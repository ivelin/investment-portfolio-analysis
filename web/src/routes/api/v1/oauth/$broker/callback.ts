import { createFileRoute } from "@tanstack/react-router";
import { isBrokerId, type BrokerId } from "@/lib/portfolio/brokers/catalog";

/**
 * Per-tenant OAuth callback for all brokers.
 * - Tenant from server-side OAuth state only (never query params)
 * - Browser session must match state.userId (blocks account-linking CSRF)
 */
export const Route = createFileRoute("/api/v1/oauth/$broker/callback")({
  server: {
    handlers: {
      GET: async ({ request, params }) => {
        const url = new URL(request.url);
        const code = url.searchParams.get("code");
        const state = url.searchParams.get("state");
        const err = url.searchParams.get("error");
        const brokerParam = params.broker;
        const origin = `${url.protocol}//${url.host}`;

        if (err) {
          return Response.redirect(
            `${origin}/connectors?oauth=error&reason=${encodeURIComponent(err)}`,
            302,
          );
        }

        if (!code || !state || !isBrokerId(brokerParam)) {
          return Response.redirect(
            `${origin}/connectors?oauth=error&reason=invalid_callback`,
            302,
          );
        }
        const broker = brokerParam as BrokerId;

        try {
          const {
            peekOAuthState,
            consumeOAuthState,
            exchangeOAuthCode,
            sealConnectorSecret,
          } = await import("@/lib/portfolio/oauth.server");
          const { getSessionUser } = await import(
            "@/lib/auth/verify.server"
          );
          const { assertOAuthCallbackPrincipal } = await import(
            "@/lib/security/oauth-callback-guard"
          );
          const { getSql } = await import("@/lib/db");
          const { newId } = await import("@/lib/security/ids");
          const { auditMeta } = await import("@/lib/security/redact");
          const { pullAndIngestBroker } = await import(
            "@/lib/portfolio/brokers/sync.server"
          );
          const { BROKERS } = await import(
            "@/lib/portfolio/brokers/catalog"
          );

          const st = await peekOAuthState({ stateId: state, broker });
          if (!st) {
            return Response.redirect(
              `${origin}/connectors?oauth=error&reason=expired_state`,
              302,
            );
          }

          const sessionUser = await getSessionUser();
          const bind = assertOAuthCallbackPrincipal({
            stateUserId: st.userId,
            sessionUserId: sessionUser?.id ?? null,
          });

          if (!bind.ok) {
            const sql = await getSql();
            await sql`
              insert into audit_events (tenant_id, user_id, action, resource_type, meta)
              values (
                ${st.tenantId},
                ${sessionUser?.id ?? null},
                ${"connector.oauth_bind_rejected"},
                ${"connector"},
                ${JSON.stringify(
                  auditMeta({
                    broker,
                    reason: bind.reason,
                    stateUserPresent: Boolean(st.userId),
                  }),
                )}::jsonb
              )
            `;
            if (bind.reason === "user_mismatch") {
              await consumeOAuthState({ stateId: state, broker });
            }
            const reason =
              bind.reason === "no_session"
                ? "sign_in_required"
                : "session_mismatch";
            return Response.redirect(
              `${origin}/connectors?oauth=error&reason=${reason}`,
              302,
            );
          }

          const consumed = await consumeOAuthState({ stateId: state, broker });
          if (!consumed) {
            return Response.redirect(
              `${origin}/connectors?oauth=error&reason=expired_state`,
              302,
            );
          }

          const tokens = await exchangeOAuthCode({
            broker,
            code,
            state: consumed,
          });

          const sql = await getSql();
          const existing = await sql<{ id: string }>`
            select id from connectors
            where tenant_id = ${consumed.tenantId} and broker = ${broker}
            limit 1
          `;
          const connectorId = existing[0]?.id ?? newId("conn");
          const def = BROKERS[broker];
          const mode =
            def.authKind === "remote_mcp" ? "remote_mcp" : "direct_oauth";

          if (!existing[0]) {
            await sql`
              insert into connectors (
                id, tenant_id, broker, mode, status, auth_kind, resource_url, mcp_url
              ) values (
                ${connectorId}, ${consumed.tenantId}, ${broker}, ${mode},
                ${"connected"}, ${def.authKind}, ${def.mcpUrl ?? null}, ${def.mcpUrl ?? null}
              )
            `;
          } else {
            await sql`
              update connectors set
                mode = ${mode},
                status = ${"connected"},
                auth_kind = ${def.authKind},
                resource_url = ${def.mcpUrl ?? null},
                mcp_url = ${def.mcpUrl ?? null},
                last_error = null,
                updated_at = now()
              where id = ${connectorId} and tenant_id = ${consumed.tenantId}
            `;
          }

          const ciphertext = sealConnectorSecret(tokens);
          await sql`
            insert into connector_secrets (connector_id, tenant_id, ciphertext, key_version)
            values (${connectorId}, ${consumed.tenantId}, ${ciphertext}, ${1})
            on conflict (connector_id) do update set
              ciphertext = excluded.ciphertext,
              tenant_id = excluded.tenant_id,
              updated_at = now()
          `;

          await sql`
            insert into audit_events (tenant_id, user_id, action, resource_type, resource_id, meta)
            values (
              ${consumed.tenantId}, ${consumed.userId}, ${"connector.oauth_completed"},
              ${"connector"}, ${connectorId},
              ${JSON.stringify(
                auditMeta({
                  broker,
                  mode,
                  authKind: def.authKind,
                  sessionBound: true,
                }),
              )}::jsonb
            )
          `;

          try {
            await pullAndIngestBroker({
              tenantId: consumed.tenantId,
              broker,
            });
          } catch {
            /* tokens saved; user can refresh */
          }

          return Response.redirect(
            `${origin}/connectors?oauth=success&broker=${broker}`,
            302,
          );
        } catch {
          return Response.redirect(
            `${origin}/connectors?oauth=error&reason=token_exchange`,
            302,
          );
        }
      },
    },
  },
});
