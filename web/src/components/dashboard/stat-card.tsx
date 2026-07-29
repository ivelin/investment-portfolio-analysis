import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "default" | "up" | "down";
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-border bg-bg-elevated p-4 sm:p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
        {label}
      </p>
      <p
        className={cn(
          "mt-2 text-2xl font-semibold tracking-tight tabular",
          tone === "up" && "text-success",
          tone === "down" && "text-danger",
        )}
      >
        {value}
      </p>
      {hint ? (
        <p className="mt-1 text-xs text-fg-muted">{hint}</p>
      ) : null}
    </div>
  );
}
