-- broker_accounts.updated_at is written by sync upserts (Schwab/MCP).
alter table broker_accounts
  add column if not exists updated_at timestamptz not null default now();
