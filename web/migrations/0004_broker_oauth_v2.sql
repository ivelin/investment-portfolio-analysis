-- Extend OAuth state for MCP OAuth 2.1 + Schwab direct; cache app DCR clients.
-- User tokens remain ONLY in connector_secrets (tenant-scoped).

alter table broker_oauth_states
  add column if not exists auth_kind text not null default 'direct_oauth';
alter table broker_oauth_states
  add column if not exists resource text;
alter table broker_oauth_states
  add column if not exists client_id text;
alter table broker_oauth_states
  add column if not exists token_endpoint text;
alter table broker_oauth_states
  add column if not exists authorization_endpoint text;
alter table broker_oauth_states
  add column if not exists scope text;
alter table broker_oauth_states
  add column if not exists meta jsonb not null default '{}'::jsonb;

-- App-level OAuth client registrations (DCR). NOT user portfolio data.
-- Safe to share across tenants; still not committed to git.
create table if not exists platform_oauth_clients (
  broker          text primary key,
  client_id       text not null,
  client_secret   text, -- null when token_endpoint_auth_method=none
  redirect_uri    text not null,
  registration    jsonb not null default '{}'::jsonb,
  updated_at      timestamptz not null default now()
);

-- Optional non-secret connector fields for remote MCP URL
alter table connectors
  add column if not exists auth_kind text;
alter table connectors
  add column if not exists resource_url text;
