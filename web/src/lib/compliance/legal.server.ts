import { getSql } from "@/lib/db";
import { newId } from "@/lib/security/ids";
import { LEGAL_PACK_VERSION } from "./legal-docs";

export type LegalStatus = {
  accepted: boolean;
  requiredVersion: string;
  acceptedAt: string | null;
};

export async function getLegalStatus(userId: string): Promise<LegalStatus> {
  const sql = await getSql();
  const rows = await sql<{ accepted_at: string }>`
    select accepted_at::text as accepted_at
    from legal_acceptances
    where user_id = ${userId}
      and document = ${"legal_pack"}
      and version = ${LEGAL_PACK_VERSION}
    limit 1
  `;
  const row = rows[0];
  return {
    accepted: Boolean(row),
    requiredVersion: LEGAL_PACK_VERSION,
    acceptedAt: row?.accepted_at ?? null,
  };
}

export async function recordLegalAcceptance(args: {
  userId: string;
  tenantId: string | null;
}): Promise<LegalStatus> {
  const sql = await getSql();
  const id = newId("legal");
  await sql`
    insert into legal_acceptances (id, user_id, tenant_id, document, version, meta)
    values (
      ${id},
      ${args.userId},
      ${args.tenantId},
      ${"legal_pack"},
      ${LEGAL_PACK_VERSION},
      ${JSON.stringify({ source: "app" })}::jsonb
    )
    on conflict (user_id, document, version) do nothing
  `;
  return getLegalStatus(args.userId);
}
