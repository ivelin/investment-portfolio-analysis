# Documentation index

Multi-tenant hosted portfolio platform. All application code is under [`web/`](../web/).

## Primary (builders)

| Document | Purpose |
|----------|---------|
| [MULTI_TENANT_ARCHITECTURE.md](MULTI_TENANT_ARCHITECTURE.md) | Tenants, Neon, REST, MCP, phases |
| [MULTI_TENANT_SECURITY.md](MULTI_TENANT_SECURITY.md) | Isolation and public-repo rules |
| [BROKER_OAUTH.md](BROKER_OAUTH.md) | Per-tenant broker OAuth |
| [../web/docs/COVERAGE.md](../web/docs/COVERAGE.md) | ≥80% critical-path coverage gate |

## Product design (future engines on tenant data)

| Document | Purpose |
|----------|---------|
| [Fund_As_Symbol_Design.md](Fund_As_Symbol_Design.md) | Account as fund symbol |
| [Capital_Efficiency_Daily_TWRR_Design.md](Capital_Efficiency_Daily_TWRR_Design.md) | Daily TWRR design |
| [TWRR_Daily_Implementation_Plan.md](TWRR_Daily_Implementation_Plan.md) | Implementation phases |

These design docs describe **product analytics** to run on multi-tenant workspace
data — not a separate single-user install.

## Root

- [README.md](../README.md) — product overview
- [SECURITY.md](../SECURITY.md) — secrets and redaction
- [HANDOFF.md](../HANDOFF.md) — deploy / agent handoff
