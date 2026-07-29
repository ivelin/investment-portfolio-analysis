-- Per-tenant OAuth state + agent API keys.
-- HARD RULE: every row is tenant-scoped. No global broker credential tables.

-- Short-lived PKCE state for broker OAuth (per tenant). code_verifier is server-only.
create table if not exists broker_oauth_states (
  id            text primary key,
  tenant_id     text not null references tenants (id) on delete cascade,
  user_id       text not null,
  broker        text not null,
  code_verifier text not null,
  redirect_uri  text not null,
  expires_at    timestamptz not null,
  created_at    timestamptz not null default now()
);
create index if not exists broker_oauth_states_tenant_idx
  on broker_oauth_states (tenant_id, broker);
create index if not exists broker_oauth_states_expires_idx
  on broker_oauth_states (expires_at);

-- Tenant API keys for MCP / REST agents (store hash only — never the raw key).
create table if not exists tenant_api_keys (
  id            text primary key,
  tenant_id     text not null references tenants (id) on delete cascade,
  user_id       text not null,
  name          text not null,
  key_prefix    text not null,
  key_hash      text not null,
  scopes        text not null default 'read', -- read | write
  last_used_at  timestamptz,
  revoked_at    timestamptz,
  created_at    timestamptz not null default now()
);
create unique index if not exists tenant_api_keys_hash_uidx on tenant_api_keys (key_hash);
create index if not exists tenant_api_keys_tenant_idx on tenant_api_keys (tenant_id);
