-- Versioned legal acceptances (Terms + Privacy pack). Fail-closed product gate.
create table if not exists legal_acceptances (
  id            text primary key,
  user_id       text not null,
  tenant_id     text references tenants (id) on delete set null,
  document      text not null,
  version       text not null,
  accepted_at   timestamptz not null default now(),
  meta          jsonb not null default '{}'::jsonb
);

create unique index if not exists legal_acceptances_user_doc_ver
  on legal_acceptances (user_id, document, version);

create index if not exists legal_acceptances_user_idx
  on legal_acceptances (user_id, accepted_at desc);
