/**
 * Schwab Trader API response contract validation + tolerant parse.
 * Detects format/version drift; never invents balances or positions.
 */

import {
  finiteNumber,
  moneyAmount,
  quantityAmount,
} from "../finance-math";

export const SCHWAB_CONTRACT_VERSION = "trader.v1.accounts.2024";

export type SchwabAccountParsed = {
  accountNumber: string;
  hashValue: string;
  type?: string;
  nickname?: string;
  liquidationValue: number | null;
  cash: number | null;
  dataQuality: number;
};

export type SchwabPositionParsed = {
  accountHash: string;
  symbol: string;
  quantity: number;
  marketValue: number | null;
  price: number | null;
  assetType: string;
  dataQuality: number;
};

export type SchwabParseResult = {
  ok: boolean;
  contractVersion: string;
  accounts: SchwabAccountParsed[];
  positions: SchwabPositionParsed[];
  warnings: string[];
  errors: string[];
  /** True when payload shape diverged enough that we should not trust a full replace. */
  contractMismatch: boolean;
  /** At least one account had usable identity (hash or number). */
  hasUsableAccounts: boolean;
};

function asRecord(v: unknown): Record<string, unknown> | null {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : null;
}

function pickString(...vals: unknown[]): string | null {
  for (const v of vals) {
    if (typeof v === "string" && v.trim()) return v.trim();
    if (typeof v === "number" && Number.isFinite(v)) return String(v);
  }
  return null;
}

/**
 * Parse accountNumbers list. Accepts array of {accountNumber, hashValue}
 * and common renames. Rejects non-array roots as contract mismatch.
 */
export function parseSchwabAccountNumbers(raw: unknown): {
  entries: Array<{ accountNumber: string; hashValue: string }>;
  warnings: string[];
  contractMismatch: boolean;
  errors: string[];
} {
  const warnings: string[] = [];
  const errors: string[] = [];
  if (raw == null) {
    return {
      entries: [],
      warnings,
      contractMismatch: true,
      errors: ["accountNumbers: null body"],
    };
  }
  // Wrapped forms
  let list: unknown = raw;
  const rec = asRecord(raw);
  if (rec) {
    if (Array.isArray(rec.accounts)) list = rec.accounts;
    else if (Array.isArray(rec.accountNumbers)) list = rec.accountNumbers;
    else if (Array.isArray(rec.data)) list = rec.data;
    else {
      return {
        entries: [],
        warnings,
        contractMismatch: true,
        errors: ["accountNumbers: expected array or {accounts|data}"],
      };
    }
  }
  if (!Array.isArray(list)) {
    return {
      entries: [],
      warnings,
      contractMismatch: true,
      errors: ["accountNumbers: not an array"],
    };
  }

  const entries: Array<{ accountNumber: string; hashValue: string }> = [];
  for (const item of list) {
    const o = asRecord(item);
    if (!o) {
      warnings.push("accountNumbers: skipped non-object entry");
      continue;
    }
    const hashValue = pickString(
      o.hashValue,
      o.hash_value,
      o.accountHash,
      o.account_hash,
      o.hash,
    );
    const accountNumber = pickString(
      o.accountNumber,
      o.account_number,
      o.accountId,
      o.account_id,
      hashValue,
    );
    if (!hashValue) {
      warnings.push("accountNumbers: entry missing hashValue");
      continue;
    }
    entries.push({
      accountNumber: accountNumber || hashValue,
      hashValue,
    });
  }

  if (list.length > 0 && entries.length === 0) {
    return {
      entries: [],
      warnings,
      contractMismatch: true,
      errors: ["accountNumbers: no parseable entries (format change?)"],
    };
  }

  return { entries, warnings, contractMismatch: false, errors };
}

function qualityFromBalances(
  nlv: number | null,
  cash: number | null,
): number {
  let q = 40;
  if (nlv != null) q += 40;
  if (cash != null) q += 20;
  return Math.min(100, q);
}

/**
 * Parse a single account payload (GET /accounts/{hash}?fields=positions).
 * Tolerates classic securitiesAccount envelope and flatter MCP-like shapes.
 */
export function parseSchwabAccountPayload(
  raw: unknown,
  identity: { accountNumber: string; hashValue: string },
): {
  account: SchwabAccountParsed | null;
  positions: SchwabPositionParsed[];
  warnings: string[];
  contractMismatch: boolean;
} {
  const warnings: string[] = [];
  const positions: SchwabPositionParsed[] = [];
  const root = asRecord(raw);
  if (!root) {
    return {
      account: null,
      positions,
      warnings: ["account payload not an object"],
      contractMismatch: true,
    };
  }

  const sa =
    asRecord(root.securitiesAccount) ||
    asRecord(root.account) ||
    root;

  const bal =
    asRecord(sa.currentBalances) ||
    asRecord(sa.balances) ||
    asRecord(root.currentBalances) ||
    {};

  const nlv = moneyAmount(
    bal.liquidationValue ??
      bal.liquidation_value ??
      bal.equity ??
      sa.liquidationValue ??
      root.liquidationValue,
  );
  const cash = moneyAmount(
    bal.cashBalance ??
      bal.cash_balance ??
      bal.cashAvailableForTrading ??
      bal.availableFunds ??
      sa.cashBalance ??
      root.cashBalance,
  );

  const type = pickString(sa.type, root.type) || undefined;
  const nickname =
    pickString(sa.nickname, root.nickname, sa.accountName) || undefined;
  const accountNumber =
    pickString(sa.accountNumber, sa.account_number, identity.accountNumber) ||
    identity.accountNumber;

  // Identity is enough to keep the account even if balances missing
  const account: SchwabAccountParsed = {
    accountNumber,
    hashValue: identity.hashValue,
    type,
    nickname,
    liquidationValue: nlv,
    cash,
    dataQuality: qualityFromBalances(nlv, cash),
  };

  const posRaw =
    (Array.isArray(sa.positions) && sa.positions) ||
    (Array.isArray(root.positions) && root.positions) ||
    [];

  let posShapeHits = 0;
  for (const p of posRaw) {
    const pr = asRecord(p);
    if (!pr) {
      warnings.push("position: non-object skipped");
      continue;
    }
    const inst = asRecord(pr.instrument) || {};
    const symbol = pickString(
      pr.symbol,
      inst.symbol,
      inst.underlyingSymbol,
      inst.cusip,
    );
    if (!symbol) {
      warnings.push("position: missing symbol");
      continue;
    }

    const longQ = quantityAmount(pr.longQuantity ?? pr.long_quantity) ?? 0;
    const shortQ = quantityAmount(pr.shortQuantity ?? pr.short_quantity) ?? 0;
    let qty = quantityAmount(
      pr.netQuantity ?? pr.quantity ?? pr.net_quantity,
    );
    if (qty == null) {
      // classic Schwab: long − short
      if (pr.longQuantity != null || pr.shortQuantity != null) {
        qty = longQ - shortQ;
        posShapeHits += 1;
      }
    } else {
      posShapeHits += 1;
    }
    if (qty == null || !Number.isFinite(qty) || qty === 0) {
      // zero qty closed position — skip
      continue;
    }

    const marketValue = moneyAmount(pr.marketValue ?? pr.market_value);
    const avg = moneyAmount(
      pr.averagePrice ?? pr.average_price ?? pr.averageLongPrice,
    );
    let price = avg;
    if (
      (price == null || price === 0) &&
      marketValue != null &&
      Math.abs(qty) > 0
    ) {
      price = Math.abs(marketValue / qty);
    }

    let qScore = 50;
    if (marketValue != null) qScore += 30;
    if (price != null) qScore += 20;

    positions.push({
      accountHash: identity.hashValue,
      symbol: symbol.toUpperCase(),
      quantity: qty,
      marketValue,
      price,
      assetType: (
        pickString(inst.assetType, pr.assetType, pr.asset_type) || "EQUITY"
      ).toLowerCase(),
      dataQuality: Math.min(100, qScore),
    });
  }

  // If positions array non-empty but zero parseable → possible format change
  const contractMismatch =
    Array.isArray(posRaw) &&
    posRaw.length > 0 &&
    positions.length === 0 &&
    posShapeHits === 0;

  if (contractMismatch) {
    warnings.push(
      "positions present but none parseable — possible API format change",
    );
  }

  return { account, positions, warnings, contractMismatch };
}

/**
 * Full portfolio parse from accountNumbers + per-account payloads.
 */
export function assembleSchwabPortfolio(args: {
  accountNumbersRaw: unknown;
  accountPayloads: Array<{
    identity: { accountNumber: string; hashValue: string };
    body: unknown;
    httpOk: boolean;
  }>;
}): SchwabParseResult {
  const warnings: string[] = [];
  const errors: string[] = [];
  const accounts: SchwabAccountParsed[] = [];
  const positions: SchwabPositionParsed[] = [];

  const nums = parseSchwabAccountNumbers(args.accountNumbersRaw);
  warnings.push(...nums.warnings);
  errors.push(...nums.errors);

  if (nums.contractMismatch) {
    return {
      ok: false,
      contractVersion: SCHWAB_CONTRACT_VERSION,
      accounts: [],
      positions: [],
      warnings,
      errors,
      contractMismatch: true,
      hasUsableAccounts: false,
    };
  }

  let anyContractMismatch = false;
  let httpFailures = 0;

  for (const payload of args.accountPayloads) {
    if (!payload.httpOk) {
      httpFailures += 1;
      warnings.push(
        `account ${payload.identity.hashValue.slice(0, 8)}…: HTTP not ok — skipped`,
      );
      continue;
    }
    const parsed = parseSchwabAccountPayload(
      payload.body,
      payload.identity,
    );
    warnings.push(...parsed.warnings);
    if (parsed.contractMismatch) anyContractMismatch = true;
    if (parsed.account) {
      accounts.push(parsed.account);
      positions.push(...parsed.positions);
    }
  }

  // All account fetches failed but numbers list was fine → transient, not contract
  if (nums.entries.length > 0 && accounts.length === 0) {
    if (httpFailures === args.accountPayloads.length) {
      errors.push("all account fetches failed");
      return {
        ok: false,
        contractVersion: SCHWAB_CONTRACT_VERSION,
        accounts: [],
        positions: [],
        warnings,
        errors,
        contractMismatch: false,
        hasUsableAccounts: false,
      };
    }
    if (anyContractMismatch) {
      errors.push("empty account list after parse — possible format change");
      return {
        ok: false,
        contractVersion: SCHWAB_CONTRACT_VERSION,
        accounts: [],
        positions: [],
        warnings,
        errors,
        contractMismatch: true,
        hasUsableAccounts: false,
      };
    }
  }

  return {
    ok: accounts.length > 0,
    contractVersion: SCHWAB_CONTRACT_VERSION,
    accounts,
    positions,
    warnings,
    errors,
    contractMismatch: anyContractMismatch && accounts.length === 0,
    hasUsableAccounts: accounts.length > 0,
  };
}

/** Guard: only persist NLV when finite (0 allowed). */
export function isPersistableNlv(v: unknown): v is number {
  const n = finiteNumber(v);
  return n != null;
}
