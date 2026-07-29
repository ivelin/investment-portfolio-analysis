"""Seed ``gt_fund_equity_snapshots`` from local Schwab export files.

Live MCP only supplies ~current equity. Account statements on disk already
contain **Net Liquidating Value** for the statement period end — real local
raw that must feed the NLV derive path (not left unused in schwab-exports/).

Never fabricates values; only parses explicit NLV / position totals from files.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from portfolio_analysis.account_nlv import resolve_account, set_account_number_last3
from portfolio_analysis.db import init_db
from portfolio_analysis.paths import broker_exports_dir, instance_home


@dataclass
class SeedResult:
    ok: bool = True
    files_scanned: int = 0
    snapshots_upserted: int = 0
    accounts_touched: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    by_account: dict[str, int] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "files_scanned": self.files_scanned,
            "snapshots_upserted": self.snapshots_upserted,
            "accounts_touched": self.accounts_touched,
            "by_account": self.by_account,
            "errors": self.errors[:20],
            "source": "local_exports",
        }


_NLV_RE = re.compile(
    r"Net\s+Liquidating\s+Value[,\"'\s]*\$?\s*([0-9][0-9,]*\.?\d*)",
    re.IGNORECASE,
)
_ACCT_HEADER_RE = re.compile(
    r"Account\s+Statement\s+for\s+(\d+)\w*\s*\(([^)]+)\)",
    re.IGNORECASE,
)
_POS_HEADER_RE = re.compile(
    r"Positions\s+for\s+account\s+(.+?)\s+\.{0,3}(\d{3})\s+as\s+of\s+.+?,\s*(\d{4}/\d{2}/\d{2})",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"[,\s$]")


def _parse_money(raw: str) -> float | None:
    try:
        return float(_MONEY_RE.sub("", raw.strip()))
    except (TypeError, ValueError):
        return None


def _as_of_from_statement_filename(name: str) -> str | None:
    # 2026-04-29-AccountStatement.csv
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else None


def _export_roots() -> list[Path]:
    roots = [
        broker_exports_dir("schwab"),
        instance_home() / "schwab-exports",
        instance_home() / "exports" / "schwab",
    ]
    out: list[Path] = []
    seen: set[Path] = set()
    for r in roots:
        try:
            rr = r.resolve()
        except OSError:
            continue
        if rr in seen or not rr.is_dir():
            continue
        seen.add(rr)
        out.append(rr)
    return out


def _resolve_export_account(
    conn: sqlite3.Connection,
    *,
    account_number: str | None,
    display_name: str | None,
    last3: str | None,
) -> tuple[str, str] | None:
    """Return (broker, account_key) or None."""
    queries: list[str] = []
    if display_name:
        queries.append(display_name.strip())
    if last3:
        queries.append(last3)
    if account_number and len(account_number) >= 3:
        queries.append(account_number[-3:])
        # also full last3 set
    for q in queries:
        resolved, _, _err = resolve_account(q, broker="schwab", conn=conn)
        if resolved is not None:
            if last3 or (account_number and len(account_number) >= 3):
                set_account_number_last3(
                    conn,
                    resolved.broker,
                    resolved.account_key,
                    last3 or account_number[-3:],  # type: ignore[index]
                )
            return resolved.broker, resolved.account_key
    return None


def _upsert_equity_snapshot(
    conn: sqlite3.Connection,
    *,
    broker: str,
    account_key: str,
    as_of_date: str,
    liquidation_value: float,
    source: str,
    data_quality: int = 95,
) -> bool:
    conn.execute(
        """
        INSERT INTO gt_fund_equity_snapshots (
            broker, account_key, as_of_date, liquidation_value, cash, source, data_quality
        ) VALUES (?, ?, ?, ?, NULL, ?, ?)
        ON CONFLICT(broker, account_key, as_of_date, source) DO UPDATE SET
            liquidation_value = excluded.liquidation_value,
            data_quality = excluded.data_quality
        """,
        (
            broker.lower(),
            account_key.lower(),
            as_of_date,
            float(liquidation_value),
            source,
            int(data_quality),
        ),
    )
    return True


def seed_from_account_statement(
    conn: sqlite3.Connection, path: Path
) -> tuple[int, str | None]:
    """Parse one statement CSV; return (rows_upserted, error)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return 0, f"{path.name}: {exc}"

    # Strip BOM
    text = text.removeprefix("\ufeff")

    m_acct = _ACCT_HEADER_RE.search(text)
    account_number = m_acct.group(1) if m_acct else None
    display_name = m_acct.group(2).strip() if m_acct else None
    last3 = account_number[-3:] if account_number and len(account_number) >= 3 else None

    m_nlv = _NLV_RE.search(text)
    if not m_nlv:
        return 0, None  # not an error — file may be positions-only extract
    nlv = _parse_money(m_nlv.group(1))
    if nlv is None or nlv < 0:
        return 0, f"{path.name}: invalid NLV"

    as_of = _as_of_from_statement_filename(path.name)
    if not as_of:
        return 0, f"{path.name}: no as_of in filename"

    resolved = _resolve_export_account(
        conn,
        account_number=account_number,
        display_name=display_name,
        last3=last3,
    )
    if resolved is None:
        return 0, f"{path.name}: no matching fund account for {display_name or last3}"

    broker, account_key = resolved
    source = f"export:statement:{path.name}"
    _upsert_equity_snapshot(
        conn,
        broker=broker,
        account_key=account_key,
        as_of_date=as_of,
        liquidation_value=nlv,
        source=source,
        data_quality=95,
    )
    return 1, None


def seed_from_positions_csv(
    conn: sqlite3.Connection, path: Path
) -> tuple[int, str | None]:
    """Sum market values from a Positions CSV as an NLV proxy for that as-of day."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return 0, f"{path.name}: {exc}"
    text = text.removeprefix("\ufeff")

    first = text.splitlines()[0] if text else ""
    m = _POS_HEADER_RE.search(first)
    display_name = None
    last3 = None
    as_of = None
    if m:
        display_name = m.group(1).strip()
        last3 = m.group(2)
        as_of = m.group(3).replace("/", "-")
    else:
        # Fallback: filename ...2026-05-27...
        m2 = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
        if m2:
            as_of = m2.group(1)
        # folder Active-Trading-IRA
        for part in path.parts:
            if "active" in part.lower() and "trading" in part.lower():
                display_name = "Active Trading IRA"
            if re.search(r"XXX(\d{3})", part, re.IGNORECASE):
                last3 = re.search(r"XXX(\d{3})", part, re.IGNORECASE).group(1)  # type: ignore[union-attr]

    if not as_of:
        return 0, None

    # Sum Mkt Val column
    import csv
    from io import StringIO

    # Skip title lines until header with Symbol
    lines = text.splitlines()
    header_i = None
    for i, line in enumerate(lines):
        if line.startswith(('"Symbol"', "Symbol")):
            header_i = i
            break
    if header_i is None:
        return 0, None
    reader = csv.DictReader(StringIO("\n".join(lines[header_i:])))
    total = 0.0
    n = 0
    for row in reader:
        # find market value key
        mv = None
        for k, v in row.items():
            if not k:
                continue
            kl = k.lower()
            if "mkt val" in kl or "market value" in kl:
                mv = v
                break
        if mv is None:
            continue
        val = _parse_money(str(mv))
        if val is None:
            continue
        total += val
        n += 1
    if n == 0:
        return 0, None

    resolved = _resolve_export_account(
        conn,
        account_number=None,
        display_name=display_name,
        last3=last3,
    )
    if resolved is None:
        return 0, f"{path.name}: no matching fund account"

    broker, account_key = resolved
    source = f"export:positions_sum:{path.name}"
    _upsert_equity_snapshot(
        conn,
        broker=broker,
        account_key=account_key,
        as_of_date=as_of,
        liquidation_value=round(total, 2),
        source=source,
        data_quality=75,  # positions sum may omit cash
    )
    return 1, None


def seed_equity_from_local_exports(
    conn: sqlite3.Connection | None = None,
    *,
    broker: str | None = "schwab",
) -> SeedResult:
    """Scan local export trees and upsert equity snapshots for known accounts."""
    own = conn is None
    db = conn if conn is not None else init_db()
    result = SeedResult()
    try:
        del broker  # reserved for future filter
        for root in _export_roots():
            for path in root.rglob("*"):
                if not path.is_file():
                    continue
                name = path.name.lower()
                if not name.endswith(".csv"):
                    continue
                result.files_scanned += 1
                n = 0
                err = None
                if (
                    "accountstatement" in name.replace(" ", "")
                    or "account_statement" in name
                ):
                    n, err = seed_from_account_statement(db, path)
                elif "position" in name:
                    n, err = seed_from_positions_csv(db, path)
                else:
                    continue
                if err:
                    result.errors.append(err)
                if n:
                    result.snapshots_upserted += n
        db.commit()
        # summarize accounts with export sources
        rows = db.execute(
            """
            SELECT account_key, COUNT(*) FROM gt_fund_equity_snapshots
            WHERE source LIKE 'export:%'
            GROUP BY 1
            """
        ).fetchall()
        for ak, c in rows:
            result.by_account[str(ak)] = int(c)
            result.accounts_touched.append(str(ak))
        result.ok = True
        return result
    finally:
        if own:
            db.close()
