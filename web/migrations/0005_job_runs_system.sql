-- Allow system-wide jobs (e.g. token_refresh across tenants) without a single tenant_id.
-- Per-connector work remains tenant-scoped in application code.

alter table job_runs drop constraint if exists job_runs_tenant_id_fkey;
alter table job_runs alter column tenant_id drop not null;
-- Re-add FK that allows NULL
alter table job_runs
  add constraint job_runs_tenant_id_fkey
  foreign key (tenant_id) references tenants (id) on delete cascade;
