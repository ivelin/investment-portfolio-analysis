import { getSql } from "@/lib/db";
import type { BrokerId } from "./catalog";

/**
 * Pull + ingest for a connected broker.
 * Phase-1 stub: marks last_sync without inventing real balances.
 * Real broker pulls land in later phases; demo data is already seeded.
 */
export async function pullAndIngestBroker(args: {
  tenantId: string;
  broker: BrokerId;
}): Promise<void> {
  const sql = await getSql();
  await sql`
    update connectors set
      last_sync_at = now(),
      last_error = null,
      updated_at = now()
    where tenant_id = ${args.tenantId} and broker = ${args.broker}
  `;
}
