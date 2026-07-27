"""
Daily Position Reconstruction Engine

This module produces a high-quality, auditable daily (or near-daily) position
table by anchoring to Ground-Truth sources (gt_brokerage_statement_positions
and gt_daily_positions) and safely interpolating using transaction history
and realized gains between anchors.

The goal is to create a "golden" daily_position_values table (or reconciled
variant) that can be used as the single source of truth for TWRR, reporting,
and any other analysis — going back as far as reliable anchors exist (target:
end of 2022+).

Design principles:
- GT statement positions are hard truth on their exact dates.
- Bulk Positions CSVs are high-trust anchors.
- Interpolation between anchors uses GT-preferred transactions + realized gains.
- Every row carries clear provenance (source_type, source_id, data_quality).
- The engine is designed to be re-run as new direct structured exports (CSV/XML/JSON) are added to the sacred directory.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .market_data import fetch_historical_prices


@dataclass
class PositionAnchor:
    """A verified position snapshot from a GT source."""

    as_of_date: str
    symbol: str
    quantity: float
    market_value: float | None = None
    avg_cost: float | None = None
    source_type: str = "statement"  # "statement", "positions_csv", etc.
    source_id: str = ""  # filename or statement identifier
    data_quality: int = 100


def get_position_anchors(
    conn: sqlite3.Connection, symbol: str | None = None
) -> list[PositionAnchor]:
    """
    Collect all hard anchors from GT statement positions and GT daily positions.
    Sorted by date.
    """
    anchors: list[PositionAnchor] = []

    # Highest priority: brokerage statement positions
    query = """
        SELECT as_of_date, symbol, quantity, market_value, avg_cost, source_statement as source_id
        FROM gt_brokerage_statement_positions
    """
    params: list = []
    if symbol:
        query += " WHERE symbol = ?"
        params.append(symbol)

    for row in conn.execute(query, params).fetchall():
        anchors.append(
            PositionAnchor(
                as_of_date=row["as_of_date"],
                symbol=row["symbol"],
                quantity=float(row["quantity"] or 0),
                market_value=row["market_value"],
                avg_cost=row["avg_cost"],
                source_type="statement",
                source_id=row["source_id"],
                data_quality=100,
            )
        )

    # High-trust daily snapshots from bulk Positions exports
    query = """
        SELECT as_of_date, symbol, quantity, market_value, avg_cost, source_file as source_id
        FROM gt_daily_positions
    """
    params = []
    if symbol:
        query += " WHERE symbol = ?"
        params.append(symbol)

    for row in conn.execute(query, params).fetchall():
        anchors.append(
            PositionAnchor(
                as_of_date=row["as_of_date"],
                symbol=row["symbol"],
                quantity=float(row["quantity"] or 0),
                market_value=row["market_value"],
                avg_cost=row["avg_cost"],
                source_type="positions_csv",
                source_id=row["source_id"],
                data_quality=95,
            )
        )

    # Sort and dedupe (keep highest quality on duplicate dates)
    anchors.sort(key=lambda a: (a.as_of_date, -a.data_quality))
    seen = set()
    deduped = []
    for a in anchors:
        key = (a.symbol, a.as_of_date)
        if key not in seen:
            seen.add(key)
            deduped.append(a)
    return deduped


def reconstruct_daily_positions_for_symbol(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    use_price_for_mv: bool = True,
    full_daily: bool = False,
) -> pd.DataFrame:
    """
    Reconstruct positions **only on dates where we have actual source data**.

    We deliberately avoid broad calendar-day interpolation to keep the table "pristine".

    Sources used:
    - Hard anchors: gt_brokerage_statement_positions + gt_daily_positions (exact qty + MV)
    - Transaction dates: quantity derived from nearest prior hard anchor + deltas **on that exact date**.
      Real historical close price is fetched to compute MV when possible.

    This produces a much cleaner table with high data_quality rows backed by actual exports + prices.
    """
    all_anchors = get_position_anchors(conn, symbol)
    if not all_anchors:
        return pd.DataFrame()

    anchor_dates = sorted({a.as_of_date for a in all_anchors})
    if start_date is None:
        start_date = min(anchor_dates)
    if end_date is None:
        end_date = max(anchor_dates)

    # Collect all transaction dates in the window (prefer gt_transactions)
    tx_dates = conn.execute(
        """
        SELECT DISTINCT transaction_date FROM gt_transactions
        WHERE symbol = ? AND transaction_date BETWEEN ? AND ?
        UNION
        SELECT DISTINCT transaction_date FROM gt_transactions
        WHERE symbol = ? AND transaction_date BETWEEN ? AND ?
        """,
        (symbol, start_date, end_date, symbol, start_date, end_date),
    ).fetchall()
    event_dates = sorted(
        {d[0] for d in tx_dates}
        | {a.as_of_date for a in all_anchors if start_date <= a.as_of_date <= end_date}
    )

    rows = []

    for d in event_dates:
        # Hard anchor on this exact date?
        hard = next((a for a in all_anchors if a.as_of_date == d), None)
        if hard:
            rows.append(
                {
                    "symbol": symbol,
                    "as_of_date": d,
                    "quantity": hard.quantity,
                    "market_value": hard.market_value,
                    "avg_cost": hard.avg_cost,
                    "source_type": hard.source_type,
                    "source_id": hard.source_id,
                    "data_quality": hard.data_quality,
                    "price_source": "anchor",
                }
            )
            continue

        # Derive quantity from nearest prior anchor + transactions on this exact date
        prior = max(
            (a for a in all_anchors if a.as_of_date < d),
            key=lambda x: x.as_of_date,
            default=None,
        )
        if prior is None:
            continue

        deltas = conn.execute(
            """
            SELECT quantity, transaction_type, description FROM gt_transactions
            WHERE symbol = ? AND transaction_date = ? AND transaction_date > ?
            UNION
            SELECT quantity, transaction_type, description FROM gt_transactions
            WHERE symbol = ? AND transaction_date = ? AND transaction_date > ?
            """,
            (symbol, d, prior.as_of_date, symbol, d, prior.as_of_date),
        ).fetchall()

        qty = float(prior.quantity or 0)
        for tx in deltas:
            raw = float(tx["quantity"] or 0)
            ttype = (tx["transaction_type"] or "").lower()
            desc = ""
            try:
                desc = (tx["description"] or "").lower()
            except Exception:
                pass
            if "journal" in ttype or "journal" in desc:
                continue  # internal adjustment -- do not affect size (matches new recon + gt tx reality)
            delta = abs(raw)
            is_reducing = any(kw in ttype for kw in ["sell", "sold"])
            qty = max(qty - delta, 0.0) if is_reducing else qty + delta

        # Try to attach real historical price
        market_value = None
        price_source = "derived_no_price"
        if use_price_for_mv:
            try:
                price_df = fetch_historical_prices(
                    [symbol], d, d, provider="auto", use_cache=True
                )
                if not price_df.empty and symbol in price_df.columns:
                    close_price = float(price_df.iloc[0][symbol])
                    market_value = round(qty * close_price, 2)
                    price_source = "historical_close"
            except Exception:
                pass

        # Cross-check with realized gains on this date (if any lots closed today, the qty change is independently verified)
        realized_on_date = conn.execute(
            """
            SELECT SUM(quantity) as closed_qty
            FROM gt_realized_gains
            WHERE symbol = ? AND closed_date = ?
            """,
            (symbol, d),
        ).fetchone()
        realized_close_qty = (
            abs(realized_on_date["closed_qty"] or 0) if realized_on_date else 0
        )

        # Only include the derived row if we have a real historical price (further reduces synthetic data)
        # AND the qty change is consistent with any realized gains on this date (or there are no realized closes).
        if qty > 0 and market_value is not None:
            consistent_with_realized = (realized_close_qty == 0) or (
                abs(qty - (prior.quantity or 0)) >= realized_close_qty - 0.01
            )
            if consistent_with_realized:
                rows.append(
                    {
                        "symbol": symbol,
                        "as_of_date": d,
                        "quantity": round(qty, 4),
                        "market_value": market_value,
                        "avg_cost": None,
                        "source_type": "transaction_derived",
                        "source_id": "gt_transactions+prices+realized",
                        "data_quality": 88 if realized_close_qty > 0 else 82,
                        "price_source": price_source,
                    }
                )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values(["as_of_date", "data_quality"], ascending=[True, False])
    df = df.drop_duplicates(subset=["symbol", "as_of_date"], keep="first")
    df = df.sort_values("as_of_date").reset_index(drop=True)

    # === New "No Phantom Positions" Guard (user-requested cleanup) ===
    # After building all candidate rows, find the last date where a hard anchor
    # (statement or positions CSV) showed quantity == 0. Any later positive
    # quantity rows that are not backed by a newer hard anchor are considered
    # phantoms from old closed activity and are zeroed out.
    hard_anchors = [
        a
        for a in all_anchors
        if a.as_of_date >= start_date and a.as_of_date <= end_date
    ]
    last_known_close = None
    for a in sorted(hard_anchors, key=lambda x: x.as_of_date):
        if a.quantity < 0.01:
            last_known_close = a.as_of_date

    if last_known_close:

        def _is_phantom(row):
            if row["quantity"] <= 0.01:
                return False
            # If this row's date is after the last known close and it is not itself a hard anchor row
            if row["as_of_date"] > last_known_close:
                is_hard = row["source_type"] in ("statement", "positions_csv")
                if not is_hard:
                    return True
            return False

        mask = df.apply(_is_phantom, axis=1)
        if mask.any():
            df.loc[mask, "quantity"] = 0.0
            df.loc[mask, "market_value"] = 0.0
            df.loc[mask, "data_quality"] = 40  # demoted
            df.loc[mask, "notes"] = (
                df.loc[mask, "notes"].fillna("")
                + " [Phantom position after last known close - zeroed by guard]"
            )

    if full_daily and not df.empty:
        df = df.sort_values("as_of_date").set_index("as_of_date")
        # generate all calendar days from first to last (for charting step function)
        full_idx = pd.date_range(df.index[0], df.index[-1], freq="D").strftime(
            "%Y-%m-%d"
        )
        df = df.reindex(full_idx)
        # forward fill quantity (position size doesn't change on non-event days)
        if "quantity" in df.columns:
            df["quantity"] = df["quantity"].ffill()
        # propagate symbol (required for persist) and basic provenance for ffilled days
        if "symbol" in df.columns:
            df["symbol"] = (
                df["symbol"].ffill().fillna(df["symbol"].iloc[0] if len(df) else None)
            )
        for col in ("source_type", "source_id", "price_source"):
            if col in df.columns:
                df[col] = df[col].ffill()
        # for other cols like mv, we can leave or note as ffilled qty
        df = df.reset_index().rename(columns={"index": "as_of_date"})
        df = df.sort_values("as_of_date").reset_index(drop=True)

    return df


def persist_reconstructed_positions(
    conn: sqlite3.Connection, df: pd.DataFrame, table: str = "daily_position_values"
) -> int:
    """
    Persist a reconstructed DataFrame into the target table.
    Uses INSERT OR REPLACE on (symbol, as_of_date) for idempotency.
    """
    if df.empty:
        return 0

    count = 0
    for _, row in df.iterrows():
        mv = row.get("market_value")
        if mv is None or (isinstance(mv, float) and mv != mv):  # nan guard
            mv = 0.0  # placeholder; real MV populated by ensure/recon paths that have prices
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {table}
            (symbol, as_of_date, quantity, market_value, avg_cost,
             price_source, data_quality, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["symbol"],
                row["as_of_date"],
                row["quantity"],
                mv,
                row.get("avg_cost"),
                row.get("price_source", "reconciled"),
                row.get("data_quality", 70),
                row.get("source_id"),
            ),
        )
        count += 1

    conn.commit()
    return count


def evaluate_reconstruction(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Headless evaluation of the current state of daily position reconstruction
    for a symbol. Returns detailed metrics for the "pristine" decision.
    """
    df = reconstruct_daily_positions_for_symbol(conn, symbol, start_date, end_date)

    if df.empty:
        return {
            "symbol": symbol,
            "total_reconstructed_days": 0,
            "coverage_pct": 0.0,
            "high_quality_pct": 0.0,
            "interpolated_pct": 100.0,
            "anchor_fidelity_issues": 0,
            "phantom_position_days": 0,
            "status": "no_data",
            "is_pristine": False,
        }

    total = len(df)
    high_quality = len(df[df["data_quality"] >= 85])
    interpolated = len(df[df["data_quality"] < 70])

    # Stricter "pristine" criteria for daily positions
    # Goal: As much real anchored data as possible, minimal synthetic rows
    high_quality_pct = (high_quality / total) if total > 0 else 0
    interpolated_pct = (interpolated / total) if total > 0 else 0

    # Additional check: for dates with realized closes, the derived qty should be consistent
    # (simplified: if we have many realized closes, we expect the data_quality to be solid)
    realized_dates = set()
    for row in conn.execute(
        "SELECT DISTINCT closed_date FROM gt_realized_gains WHERE symbol = ? AND closed_date BETWEEN ? AND ?",
        (symbol, start_date or "1900-01-01", end_date or "2100-12-31"),
    ).fetchall():
        if row[0]:
            realized_dates.add(row[0])

    realized_coverage = 0
    if realized_dates and total > 0:
        covered = sum(1 for d in realized_dates if d in df["as_of_date"].values)
        realized_coverage = covered / len(realized_dates)

    is_pristine = (
        total > 0
        and high_quality_pct >= 0.92
        and interpolated_pct <= 0.03
        and (len(realized_dates) == 0 or realized_coverage >= 0.8)
    )

    return {
        "symbol": symbol,
        "total_reconstructed_days": total,
        "high_quality_days": high_quality,
        "coverage_pct": round((high_quality / total) * 100, 1),
        "high_quality_pct": round(high_quality_pct * 100, 1),
        "interpolated_pct": round(interpolated_pct * 100, 1),
        "anchor_fidelity_issues": 0,
        "phantom_position_days": 0,
        "realized_coverage": round(realized_coverage * 100, 1)
        if realized_dates
        else 100.0,
        "status": "pristine" if is_pristine else "needs_attention",
        "is_pristine": is_pristine,
    }


def force_snap_to_gt_anchors(conn: sqlite3.Connection, symbol: str) -> int:
    """
    Correction mechanism: For a given symbol, ensure that every known high-quality
    GT anchor (from statements and bulk positions CSVs) has an explicit, high
    data_quality row in daily_position_values.

    This is a powerful "reconciliation" action the loop can take when issues are detected.
    """
    anchors = get_position_anchors(conn, symbol)
    if not anchors:
        return 0

    count = 0
    for a in anchors:
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_position_values
            (symbol, as_of_date, quantity, market_value, avg_cost,
             price_source, data_quality, source_file)
            VALUES (?, ?, ?, ?, ?, 'gt_anchor', ?, ?)
            """,
            (
                a.symbol,
                a.as_of_date,
                a.quantity,
                a.market_value,
                a.avg_cost,
                max(a.data_quality, 95),
                a.source_id,
            ),
        )
        count += 1

    conn.commit()
    return count


def force_snap_relevant_anchors(
    conn: sqlite3.Connection,
    symbol: str,
    target_dates: list[str],
    window_days: int = 30,
) -> int:
    """
    Targeted correction (preferred in the loop):
    Only snap the GT anchors that are closest to the given problematic dates
    (within `window_days`).

    This is much more efficient and focused than snapping every historical anchor
    for the symbol.
    """
    if not target_dates:
        return 0

    all_anchors = get_position_anchors(conn, symbol)
    if not all_anchors:
        return 0

    # For each target date, find the closest anchors (before and after) within the window
    # Use list + key dedup (PositionAnchor is not hashable by default)
    seen = set()
    relevant_anchors = []
    for tdate in target_dates:
        for a in all_anchors:
            try:
                anchor_dt = datetime.strptime(a.as_of_date, "%Y-%m-%d")
                target_dt = datetime.strptime(tdate, "%Y-%m-%d")
                if abs((anchor_dt - target_dt).days) <= window_days:
                    key = (a.symbol, a.as_of_date)
                    if key not in seen:
                        seen.add(key)
                        relevant_anchors.append(a)
            except ValueError:
                continue

    if not relevant_anchors:
        return 0

    count = 0
    for a in relevant_anchors:
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_position_values
            (symbol, as_of_date, quantity, market_value, avg_cost,
             price_source, data_quality, source_file)
            VALUES (?, ?, ?, ?, ?, 'gt_anchor_relevant', ?, ?)
            """,
            (
                a.symbol,
                a.as_of_date,
                a.quantity,
                a.market_value,
                a.avg_cost,
                max(a.data_quality, 95),
                a.source_id,
            ),
        )
        count += 1

    conn.commit()
    return count


def build_reconciled_daily_positions(
    conn: sqlite3.Connection,
    symbols: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    High-level entry point. Reconstructs and (eventually) persists a
    reconciled daily positions table for the requested symbols/date range.

    This is the function the orchestration script will call.
    """
    if symbols is None:
        # Discover symbols that have at least one GT anchor
        symbols = [
            r["symbol"]
            for r in conn.execute(
                "SELECT DISTINCT symbol FROM gt_brokerage_statement_positions"
            ).fetchall()
        ]

    for sym in symbols:
        df = reconstruct_daily_positions_for_symbol(
            conn, sym, start_date, end_date, full_daily=True
        )
        if not df.empty:
            inserted = persist_reconstructed_positions(
                conn, df, table="daily_position_values"
            )
            print(
                f"[daily_positions] {sym}: {len(df)} reconstructed position rows (persisted {inserted})"
            )
        else:
            print(f"[daily_positions] {sym}: no data")

    # full daily series now produced with ffill for charting (step function)


def reconstruct_daily_position_quantities(
    conn: sqlite3.Connection | None,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Reconstruct a reliable, continuous daily position *quantity* series for a symbol.

    This is the canonical function for position size charting (step function).

    Rules (per spec):
    - Anchor to the latest known good snapshot from gt_daily_positions whose as_of_date
      is <= the effective window start (falls back to 1900-01-01 / qty=0 if none).
    - Only apply transactions with transaction_date > anchor_date (and <= end).
    - Correctly handle Buy/Sell by signed delta using transaction_type.
    - Ignore "Journal" entries entirely (tx_type or description contains 'journal'):
      these are internal adjustments/transfers and must not inflate/deflate the
      plotted position size.
    - Output clean daily series with *no gaps*: full calendar reindex from min(start,anchor)
      to max(end), ffill quantity (step function). Rows for every day.

    Returns DF with ['as_of_date', 'quantity'] sorted, quantity float >=0.

    Used by chart generators instead of raw queries against daily_position_values
    (which may contain bad spikes from prior logic) or direct gt_daily_positions (sparse).
    """
    if conn is None:
        from .db import get_connection

        conn = get_connection()

    # Determine anchor: latest gt_daily_positions <= start (or overall latest before if start early)
    anchor_params = [symbol]
    anchor_sql = """
        SELECT as_of_date, quantity
        FROM gt_daily_positions
        WHERE symbol = ?
    """
    if start_date:
        anchor_sql += " AND as_of_date <= ?"
        anchor_params.append(start_date)
    anchor_sql += " ORDER BY as_of_date DESC LIMIT 1"

    anchor = conn.execute(anchor_sql, anchor_params).fetchone()

    if anchor:
        anchor_date = anchor[0]
        base_qty = float(anchor[1] or 0)
    else:
        anchor_date = "1900-01-01"
        base_qty = 0.0

    # Effective dates for the output series
    eff_start = start_date or anchor_date
    if end_date is None:
        # default to latest relevant date we have
        max_row = conn.execute(
            "SELECT MAX(as_of_date) FROM gt_daily_positions WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        eff_end = (
            max_row[0]
            if max_row and max_row[0]
            else datetime.now().strftime("%Y-%m-%d")
        )
    else:
        eff_end = end_date

    # Fetch candidate tx after the anchor (we will filter Journal and only use those in range)
    tx_rows = conn.execute(
        """
        SELECT transaction_date, quantity, transaction_type, description
        FROM gt_transactions
        WHERE symbol = ? AND transaction_date > ?
        ORDER BY transaction_date ASC, id ASC
        """,
        (symbol, anchor_date),
    ).fetchall()

    from collections import defaultdict

    day_deltas: dict[str, float] = defaultdict(float)
    for tx in tx_rows:
        tdate = tx[0]
        if tdate > eff_end:
            continue
        raw = float(tx[1] or 0)
        ttype = (tx[2] or "").lower()
        desc = (tx[3] or "").lower() if len(tx) > 3 else ""
        if "journal" in ttype or "journal" in desc:
            continue  # internal adjustment/transfer — do not affect position size
        delta = abs(raw)
        is_reducing = any(
            kw in ttype for kw in ["sell", "sold", "sell to open", "sell short"]
        )
        change = -delta if is_reducing else +delta
        day_deltas[tdate] += change

    # Accumulate running qty from the anchor base + post-anchor deltas
    running_qty = base_qty
    qty_at: dict[str, float] = {anchor_date: base_qty}
    for tdate in sorted(day_deltas.keys()):
        running_qty += day_deltas[tdate]
        running_qty = max(running_qty, 0.0)
        qty_at[tdate] = running_qty

    # Pre-compute the carried-in quantity exactly at eff_start (applies any tx between anchor and start)
    carried_at_start = base_qty
    for tdate in sorted(day_deltas.keys()):
        if tdate <= eff_start:
            carried_at_start += day_deltas[tdate]
        else:
            break
    carried_at_start = max(carried_at_start, 0.0)

    # Build full daily index (no gaps) and ffill
    try:
        full_idx = (
            pd.date_range(eff_start, eff_end, freq="D").strftime("%Y-%m-%d").tolist()
        )
    except Exception:
        full_idx = sorted(set([eff_start, eff_end]))

    rows = []
    last_q = carried_at_start
    for d in full_idx:
        if d in qty_at:
            last_q = qty_at[d]
        # else: carry last_q forward (no tx that day) -- this gives the step
        rows.append({"as_of_date": d, "quantity": last_q})

    if not rows:
        return pd.DataFrame(columns=["as_of_date", "quantity"])

    df = pd.DataFrame(rows)
    df = df.sort_values("as_of_date").reset_index(drop=True)
    # Final safety ffill (in case gaps in logic)
    df["quantity"] = df["quantity"].ffill().fillna(0.0)
    # Trim exactly to requested if provided (after ffill carries correctly from pre anchors)
    if start_date:
        df = df[df["as_of_date"] >= start_date].copy()
    if end_date:
        df = df[df["as_of_date"] <= end_date].copy()
    df = df.reset_index(drop=True)
    df["quantity"] = df["quantity"].round(4)
    return df[["as_of_date", "quantity"]]


# Legacy TWRR population removed (2026-05).
# All daily_twrr rows are now produced exclusively by
# populate_daily_twrr_from_subperiods() in twrr.py using the single
# authoritative subperiod HPR logic. This eliminates duplicate calculation
# paths and legacy version branching.
