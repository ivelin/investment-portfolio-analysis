import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FundSeriesPoint } from "@/lib/portfolio/types";
import { formatUsd } from "@/lib/utils";

export function NlvChart({ series }: { series: FundSeriesPoint[] }) {
  if (!series.length) {
    return (
      <div className="flex h-64 items-center justify-center rounded-[var(--radius-lg)] border border-border bg-bg-elevated text-sm text-fg-muted">
        No fund series yet
      </div>
    );
  }

  const data = series.map((p) => ({
    date: p.asOfDate.slice(5),
    fullDate: p.asOfDate,
    nlv: p.liquidationValue,
    index: p.twrrIndex,
  }));

  return (
    <div className="h-64 w-full sm:h-72">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="nlvFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#c8ccd4" stopOpacity={0.22} />
              <stop offset="100%" stopColor="#c8ccd4" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#27272a" strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            minTickGap={28}
          />
          <YAxis
            tick={{ fill: "#71717a", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={(v: number) =>
              v >= 1000 ? `$${(v / 1000).toFixed(0)}k` : `$${v}`
            }
          />
          <Tooltip
            contentStyle={{
              background: "#121214",
              border: "1px solid #27272a",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#a1a1aa" }}
            formatter={(value: number) => [formatUsd(value), "NLV"]}
            labelFormatter={(_, payload) =>
              (payload?.[0]?.payload as { fullDate?: string } | undefined)
                ?.fullDate ?? ""
            }
          />
          <Area
            type="monotone"
            dataKey="nlv"
            stroke="#c8ccd4"
            strokeWidth={1.5}
            fill="url(#nlvFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
