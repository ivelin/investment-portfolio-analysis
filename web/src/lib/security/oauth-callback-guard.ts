export type OAuthBindOk = { ok: true };
export type OAuthBindFail = {
  ok: false;
  reason: "no_session" | "user_mismatch" | "missing_state_user";
};
export type OAuthBindResult = OAuthBindOk | OAuthBindFail;

/**
 * Fail-closed bind: OAuth state user must match the browser session user.
 * Tenant is never taken from the client — only from server-side state.
 */
export function assertOAuthCallbackPrincipal(args: {
  stateUserId: string | null | undefined;
  sessionUserId: string | null | undefined;
}): OAuthBindResult {
  if (!args.stateUserId) {
    return { ok: false, reason: "missing_state_user" };
  }
  if (!args.sessionUserId) {
    return { ok: false, reason: "no_session" };
  }
  if (args.stateUserId !== args.sessionUserId) {
    return { ok: false, reason: "user_mismatch" };
  }
  return { ok: true };
}
