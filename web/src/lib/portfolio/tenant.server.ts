import { getSql } from "@/lib/db";
import { newId } from "@/lib/security/ids";

export type TenantRow = {
  id: string;
  ownerUserId: string;
  name: string;
  slug: string;
  plan: string;
};

function slugify(userId: string): string {
  const base = userId
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 24);
  return `u-${base || "user"}`;
}

/** Ensure a personal workspace exists for the user and seed demo fund once. */
export async function ensurePersonalTenant(userId: string): Promise<TenantRow> {
  const sql = await getSql();
  const existing = await sql<{
    id: string;
    owner_user_id: string;
    name: string;
    slug: string;
    plan: string;
  }>`
    select id, owner_user_id, name, slug, plan
    from tenants
    where owner_user_id = ${userId}
    order by created_at asc
    limit 1
  `;
  if (existing[0]) {
    await sql`
      insert into tenant_members (tenant_id, user_id, role)
      values (${existing[0].id}, ${userId}, ${"owner"})
      on conflict do nothing
    `;
    return {
      id: existing[0].id,
      ownerUserId: existing[0].owner_user_id,
      name: existing[0].name,
      slug: existing[0].slug,
      plan: existing[0].plan,
    };
  }

  const id = newId("ten");
  let slug = slugify(userId);
  const clash = await sql`select id from tenants where slug = ${slug} limit 1`;
  if (clash[0]) slug = `${slug}-${id.slice(-6)}`;

  await sql`
    insert into tenants (id, owner_user_id, name, slug, plan)
    values (${id}, ${userId}, ${"Personal workspace"}, ${slug}, ${"free"})
  `;
  await sql`
    insert into tenant_members (tenant_id, user_id, role)
    values (${id}, ${userId}, ${"owner"})
  `;

  const { seedDemoPortfolio } = await import("./service.server");
  await seedDemoPortfolio(id);

  return {
    id,
    ownerUserId: userId,
    name: "Personal workspace",
    slug,
    plan: "free",
  };
}

export async function requireTenantMembership(
  tenantId: string,
  userId: string,
): Promise<void> {
  const sql = await getSql();
  const rows = await sql`
    select 1 from tenant_members
    where tenant_id = ${tenantId} and user_id = ${userId}
    limit 1
  `;
  if (!rows[0]) {
    const err = new Error("Forbidden");
    (err as Error & { status?: number }).status = 403;
    throw err;
  }
}
