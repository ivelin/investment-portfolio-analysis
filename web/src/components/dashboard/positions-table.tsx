import type { PositionRow } from "@/lib/portfolio/types";
import { formatPct, formatUsdPrecise } from "@/lib/utils";

export function PositionsTable({ positions }: { positions: PositionRow[] }) {
  if (!positions.length) {
    return (
      <p className="text-sm text-fg-muted">No positions for this account.</p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-fg-subtle">
            <th className="pb-2 pr-3 font-medium">Symbol</th>
            <th className="pb-2 pr-3 font-medium">Type</th>
            <th className="pb-2 pr-3 text-right font-medium">Qty</th>
            <th className="pb-2 pr-3 text-right font-medium">Price</th>
            <th className="pb-2 pr-3 text-right font-medium">Mkt value</th>
            <th className="pb-2 text-right font-medium">Weight</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <tr
              key={p.symbol}
              className="border-b border-border/60 last:border-0"
            >
              <td className="py-2.5 pr-3 font-medium tabular">{p.symbol}</td>
              <td className="py-2.5 pr-3 text-fg-muted">
                {p.assetType ?? "—"}
              </td>
              <td className="py-2.5 pr-3 text-right tabular text-fg-muted">
                {p.quantity.toLocaleString()}
              </td>
              <td className="py-2.5 pr-3 text-right tabular">
                {formatUsdPrecise(p.price)}
              </td>
              <td className="py-2.5 pr-3 text-right tabular">
                {formatUsdPrecise(p.marketValue)}
              </td>
              <td className="py-2.5 text-right tabular text-fg-muted">
                {formatPct(p.weightPct, 1).replace("+", "")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
