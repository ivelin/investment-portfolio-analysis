-- Multi-tenant portfolio platform schema.
--
-- HARD RULES (public repo + hosted multi-tenant):
-- 1. Every tenant-owned row carries tenant_id TEXT NOT NULL.
-- 2. account_key is an opaque server-generated id — NEVER a raw brokerage account number.
-- 3. account_mask is display-only (e.g. …001); never store full unredacted account numbers.
-- 4. Credentials/tokens live ONLY in connector_secrets (encrypted blob) — never in logs/API dumps.
-- 5. No personal PII columns beyond Better Auth's user table (name/email from identity provider).

-- Workspace / tenant (one user can own many; future: invite collaborators)
create table if not exists tenants (
  id          text primary key,
  owner_user_id text not null,
  name        text not null,
  slug        text not null,
  plan        text not null default 'free',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create unique index if not exists tenants_slug_uidx on tenants (slug);
create index if not exists tenants_owner_idx on tenants (owner_user_id);

create table if not exists tenant_members (
  tenant_id   text not null references tenants (id) on delete cascade,
  user_id     text not null,
  role        text not null default 'owner', -- owner | admin | member | viewer
  created_at  timestamptz not null default now(),
  primary key (tenant_id, user_id)
);
create index if not exists tenant_members_user_idx on tenant_members (user_id);

-- Broker accounts (fund-as-symbol foundation). account_key is opaque.
create table if not exists broker_accounts (
  id              text primary key,
  tenant_id       text not null references tenants (id) on delete cascade,
  broker          text not null,          -- schwab | ibkr | robinhood | fidelity | synthetic
  account_key     text not null,          -- opaque uuid-like key (NOT the real account number)
  account_mask    text not null default '', -- e.g. …001 for UI only
  display_name    text not null,
  currency        text not null default 'USD',
  fund_symbol     text not null,          -- FUND:{broker}:{account_key}
  is_demo         boolean not null default false,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (tenant_id, broker, account_key)
);
create index if not exists broker_accounts_tenant_idx on broker_accounts (tenant_id);

-- Connector config (non-secret). Secrets go in connector_secrets.
create table if not exists connectors (
  id            text primary key,
  tenant_id     text not null references tenants (id) on delete cascade,
  broker        text not null,
  mode          text not null default 'exports_only', -- exports_only | mcp | direct | auto
  mcp_url       text,  -- optional remote MCP URL (no secrets)
  status        text not null default 'disconnected', -- disconnected | connected | error
  last_sync_at  timestamptz,
  last_error    text,  -- redacted error message only
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (tenant_id, broker)
);
create index if not exists connectors_tenant_idx on connectors (tenant_id);

-- Encrypted credential blobs. Application encrypts before write; never select * to clients.
create table if not exists connector_secrets (
  connector_id  text primary key references connectors (id) on delete cascade,
  tenant_id     text not null references tenants (id) on delete cascade,
  ciphertext    text not null,  -- base64 ciphertext (app-level envelope)
  key_version   integer not null default 1,
  updated_at    timestamptz not null default now()
);

-- Ground-truth daily account positions (tenant-scoped)
create table if not exists gt_account_positions (
  id            bigserial primary key,
  tenant_id     text not null references tenants (id) on delete cascade,
  account_id    text not null references broker_accounts (id) on delete cascade,
  as_of_date    date not null,
  symbol        text not null,
  quantity      double precision not null,
  market_value  double precision,
  price         double precision,
  cost_basis    double precision,
  asset_type    text,
  currency      text not null default 'USD',
  source        text not null default 'demo',
  ingested_at   timestamptz not null default now(),
  unique (tenant_id, account_id, as_of_date, symbol, source)
);
create index if not exists gt_acct_pos_tenant_date_idx
  on gt_account_positions (tenant_id, as_of_date);
create index if not exists gt_acct_pos_acct_date_idx
  on gt_account_positions (account_id, as_of_date);

-- Fund equity snapshots (account NLV anchors)
create table if not exists gt_fund_equity_snapshots (
  id                  bigserial primary key,
  tenant_id           text not null references tenants (id) on delete cascade,
  account_id          text not null references broker_accounts (id) on delete cascade,
  as_of_date          date not null,
  liquidation_value   double precision not null,
  cash                double precision,
  source              text not null default 'demo',
  data_quality        integer not null default 100,
  ingested_at         timestamptz not null default now(),
  unique (tenant_id, account_id, as_of_date, source)
);
create index if not exists gt_fund_snap_tenant_date_idx
  on gt_fund_equity_snapshots (tenant_id, as_of_date);

-- External cash flows for account-level TWRR
create table if not exists gt_fund_cash_flows (
  id            bigserial primary key,
  tenant_id     text not null references tenants (id) on delete cascade,
  account_id    text not null references broker_accounts (id) on delete cascade,
  flow_date     date not null,
  amount        double precision not null,
  flow_type     text not null, -- deposit | withdrawal | fee | transfer
  source        text not null default 'demo',
  notes         text,
  ingested_at   timestamptz not null default now()
);
create index if not exists gt_fund_cf_tenant_date_idx
  on gt_fund_cash_flows (tenant_id, flow_date);

-- Derived daily fund series (cash-flow-neutral TWRR index)
create table if not exists fund_daily (
  id                  bigserial primary key,
  tenant_id           text not null references tenants (id) on delete cascade,
  account_id          text not null references broker_accounts (id) on delete cascade,
  fund_symbol         text not null,
  as_of_date          date not null,
  liquidation_value   double precision not null,
  external_cf         double precision not null default 0,
  daily_return        double precision,
  twrr_index          double precision not null,
  data_quality        integer not null default 100,
  calc_version        text not null default 'fund-hpr-v1',
  calc_timestamp      timestamptz not null default now(),
  unique (tenant_id, fund_symbol, as_of_date)
);
create index if not exists fund_daily_tenant_symbol_date_idx
  on fund_daily (tenant_id, fund_symbol, as_of_date);

-- Job run status (no secrets, no balances)
create table if not exists job_runs (
  id            text primary key,
  tenant_id     text not null references tenants (id) on delete cascade,
  job_name      text not null,
  status        text not null default 'queued', -- queued | running | success | error
  started_at    timestamptz,
  finished_at   timestamptz,
  message       text,  -- redacted status only
  created_at    timestamptz not null default now()
);
create index if not exists job_runs_tenant_idx on job_runs (tenant_id, created_at desc);

-- Audit log for security-sensitive actions (no payload secrets)
create table if not exists audit_events (
  id            text primary key,
  tenant_id     text not null references tenants (id) on delete cascade,
  actor_user_id text,
  action        text not null,
  resource_type text,
  resource_id   text,
  meta          jsonb,
  created_at    timestamptz not null default now()
);
create index if not exists audit_events_tenant_idx on audit_events (tenant_id, created_at desc);
