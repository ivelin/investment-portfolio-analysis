/**
 * Grounded financial arithmetic for NLV, returns, and weights.
 * Rule: never invent numbers. Null in → null out. Incomplete sums are flagged.
 */

/** Coerce to a finite number or null (rejects NaN, ±Infinity, non-numeric). */
export function finiteNumber(value: unknown): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** Strict money amount: finite number (may be negative for shorts/P&L). */
export function moneyAmount(value: unknown): number | null {
  return finiteNumber(value);
}

/** Quantity: finite and not NaN; zero allowed; null rejected for writes. */
export function quantityAmount(value: unknown): number | null {
  return finiteNumber(value);
}

export type NlvAggregate = {
  /** Sum of known finite NLVs only. Null if none known. */
  total: number | null;
  knownCount: number;
  missingCount: number;
  /** True when every input had a finite NLV (including empty list → true with total null). */
  complete: boolean;
};

/**
 * Sum account NLVs without treating missing as zero.
 * Empty list → { total: null, known: 0, missing: 0, complete: true }.
 */
export function sumKnownNlvs(
  values: ReadonlyArray<number | null | undefined>,
): NlvAggregate {
  if (values.length === 0) {
    return { total: null, knownCount: 0, missingCount: 0, complete: true };
  }
  let total = 0;
  let knownCount = 0;
  let missingCount = 0;
  for (const v of values) {
    const n = finiteNumber(v);
    if (n == null) {
      missingCount += 1;
      continue;
    }
    total += n;
    knownCount += 1;
  }
  if (knownCount === 0) {
    return {
      total: null,
      knownCount: 0,
      missingCount,
      complete: false,
    };
  }
  return {
    total,
    knownCount,
    missingCount,
    complete: missingCount === 0,
  };
}

export type FundPointLike = {
  liquidationValue: number | null | undefined;
  twrrIndex?: number | null | undefined;
  asOfDate?: string;
};

/**
 * Period return % from an ordered series (oldest → newest).
 * - Needs ≥2 points with finite positive starting NLV
 * - Prefers TWRR index when both endpoints are finite, positive, and differ
 * - Falls back to NLV ratio when TWRR is unusable
 * - Never returns a fabricated 0% from a single sync day
 */
export function periodReturnPct(
  series: ReadonlyArray<FundPointLike>,
): number | null {
  if (series.length < 2) return null;

  const first = series[0];
  const last = series[series.length - 1];
  const firstNlv = finiteNumber(first.liquidationValue);
  const lastNlv = finiteNumber(last.liquidationValue);
  if (firstNlv == null || lastNlv == null) return null;
  if (!(firstNlv > 0)) return null;

  const firstIdx = finiteNumber(first.twrrIndex);
  const lastIdx = finiteNumber(last.twrrIndex);
  if (
    firstIdx != null &&
    lastIdx != null &&
    firstIdx > 0 &&
    lastIdx > 0 &&
    Math.abs(lastIdx - firstIdx) > 1e-9
  ) {
    return (lastIdx / firstIdx - 1) * 100;
  }

  // Distinct calendar days only for NLV ratio (same-day re-sync is not a period)
  if (first.asOfDate && last.asOfDate && first.asOfDate === last.asOfDate) {
    return null;
  }

  return (lastNlv / firstNlv - 1) * 100;
}

/**
 * Daily return from previous → current NLV (simple, no external CF).
 * Null when previous NLV missing/non-positive or current missing.
 */
export function dailyReturnFromNlv(
  prevNlv: unknown,
  currentNlv: unknown,
): number | null {
  const prev = finiteNumber(prevNlv);
  const curr = finiteNumber(currentNlv);
  if (prev == null || curr == null || !(prev > 0)) return null;
  return curr / prev - 1;
}

export function nextTwrrIndex(
  prevIndex: unknown,
  dailyReturn: number | null,
): number | null {
  const prev = finiteNumber(prevIndex);
  if (prev == null || !(prev > 0)) return null;
  if (dailyReturn == null) return prev;
  if (!Number.isFinite(dailyReturn)) return null;
  return prev * (1 + dailyReturn);
}

export type PositionWeightInput = {
  marketValue: number | null | undefined;
};

/**
 * Weight % of each position vs sum of finite market values.
 * Null weight when total is zero/missing or row MV missing.
 */
export function positionWeights(
  rows: ReadonlyArray<PositionWeightInput>,
): Array<number | null> {
  const mvs = rows.map((r) => finiteNumber(r.marketValue));
  let total = 0;
  let known = 0;
  for (const mv of mvs) {
    if (mv == null) continue;
    total += mv;
    known += 1;
  }
  if (known === 0 || total === 0) {
    return rows.map(() => null);
  }
  return mvs.map((mv) => {
    if (mv == null) return null;
    return (mv / total) * 100;
  });
}

/**
 * Flag when position MV sum disagrees materially with account NLV.
 * Does not correct either side — analysis only.
 */
export function positionsVsNlvCheck(
  positionMarketValues: ReadonlyArray<number | null | undefined>,
  accountNlv: number | null | undefined,
  opts: { tolerancePct?: number } = {},
): {
  ok: boolean;
  positionsSum: number | null;
  accountNlv: number | null;
  deltaPct: number | null;
  reason: string | null;
} {
  const nlv = finiteNumber(accountNlv);
  const agg = sumKnownNlvs(positionMarketValues);
  if (nlv == null) {
    return {
      ok: true,
      positionsSum: agg.total,
      accountNlv: null,
      deltaPct: null,
      reason: "account_nlv_unknown",
    };
  }
  if (agg.total == null) {
    return {
      ok: true,
      positionsSum: null,
      accountNlv: nlv,
      deltaPct: null,
      reason: "positions_empty_or_unknown",
    };
  }
  const tol = opts.tolerancePct ?? 25;
  if (!(Math.abs(nlv) > 1e-6)) {
    return {
      ok: Math.abs(agg.total) < 1,
      positionsSum: agg.total,
      accountNlv: nlv,
      deltaPct: null,
      reason: Math.abs(agg.total) < 1 ? null : "nlv_near_zero_positions_nonzero",
    };
  }
  const deltaPct = ((agg.total - nlv) / Math.abs(nlv)) * 100;
  const ok = Math.abs(deltaPct) <= tol;
  return {
    ok,
    positionsSum: agg.total,
    accountNlv: nlv,
    deltaPct,
    reason: ok ? null : "positions_nlv_divergence",
  };
}
