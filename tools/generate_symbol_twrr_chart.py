#!/usr/bin/env python3
"""
Enhanced Symbol TWRR + OHLC + Position Size Chart Generator

Supports --annotate-trades to overlay Buy/Sell markers on the TWRR line.
Uses the canonical reconstruct_daily_position_quantities() from the refactored engine.
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Rectangle
from portfolio_analysis.daily_positions import reconstruct_daily_position_quantities


def generate_symbol_chart(
    symbol: str,
    start_date: str = None,
    end_date: str = None,
    output: Path = None,
    annotate_trades: bool = False,
) -> Path:
    from portfolio_analysis.paths import default_db_path

    db_path = default_db_path()
    conn = sqlite3.connect(db_path)

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if start_date is None:
        start_date = "2026-01-01"

    # TWRR data
    twrr_df = pd.read_sql_query(
        """
        SELECT as_of_date, daily_return
        FROM daily_twrr
        WHERE symbol = ? AND as_of_date BETWEEN ? AND ?
        ORDER BY as_of_date
        """,
        conn,
        params=[symbol, start_date, end_date],
    )

    # OHLC
    ohlc_df = pd.read_sql_query(
        """
        SELECT date, open, high, low, close
        FROM market_price_bars
        WHERE symbol = ? AND date BETWEEN ? AND ?
        ORDER BY date
        """,
        conn,
        params=[symbol, start_date, end_date],
    )

    # Position size (canonical recon)
    pos_df = reconstruct_daily_position_quantities(
        conn, symbol, start_date=start_date, end_date=end_date
    )

    # Trades (for annotation)
    trades_df = pd.DataFrame()
    if annotate_trades:
        trades_df = pd.read_sql_query(
            """
            SELECT transaction_date, transaction_type, quantity, price
            FROM gt_transactions
            WHERE symbol = ? AND transaction_date BETWEEN ? AND ?
              AND transaction_type IN ('Buy', 'Sell')
            ORDER BY transaction_date
            """,
            conn,
            params=[symbol, start_date, end_date],
        )

    conn.close()

    # Prep
    twrr_df["as_of_date"] = pd.to_datetime(twrr_df["as_of_date"])
    twrr_df["cum_twrr"] = (1 + twrr_df["daily_return"]).cumprod() - 1
    ohlc_df["date"] = pd.to_datetime(ohlc_df["date"])
    pos_df["as_of_date"] = pd.to_datetime(pos_df["as_of_date"])

    # Plot
    fig, (ax1, ax2, ax3) = plt.subplots(
        3,
        1,
        figsize=(14, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [1, 1.2, 0.8]},
    )

    # Panel 1: TWRR
    ax1.plot(
        twrr_df["as_of_date"],
        twrr_df["cum_twrr"] * 100,
        color="#1f77b4",
        linewidth=1.8,
        label="Cumulative TWRR %",
    )
    ax1.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax1.set_ylabel("Cumul. TWRR %")
    ax1.set_title(
        f"{symbol} — TWRR / OHLC / Position Size (anchored recon)",
        fontsize=12,
        fontweight="bold",
    )
    ax1.grid(True, alpha=0.3)

    # Trade annotations on TWRR line
    if annotate_trades and not trades_df.empty:
        twrr_dates = pd.to_datetime(twrr_df["as_of_date"])
        for _, row in trades_df.iterrows():
            tdate = pd.Timestamp(row["transaction_date"])
            nearest_idx = (twrr_dates - tdate).abs().argmin()
            marker_x = twrr_dates.iloc[nearest_idx]
            marker_y = twrr_df.iloc[nearest_idx]["cum_twrr"] * 100

            color = "#2ca02c" if row["transaction_type"] == "Buy" else "#d62728"
            marker = "^" if row["transaction_type"] == "Buy" else "v"
            ax1.scatter(
                marker_x,
                marker_y,
                color=color,
                marker=marker,
                s=55,
                zorder=5,
                edgecolors="black",
                linewidths=0.4,
            )

    # Panel 2: OHLC
    for _, row in ohlc_df.iterrows():
        d, o, h, lo, c = (
            row["date"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
        )
        color = "#2ca02c" if c >= o else "#d62728"
        ax2.plot([d, d], [lo, h], color=color, linewidth=0.8)
        rect = Rectangle(
            (d - pd.Timedelta(days=0.4), min(o, c)),
            pd.Timedelta(days=0.8),
            abs(c - o),
            facecolor=color,
            edgecolor=color,
            linewidth=0.3,
        )
        ax2.add_patch(rect)
    ax2.set_ylabel(f"{symbol} Price")
    ax2.grid(True, alpha=0.3)

    # Panel 3: Position Size
    ax3.step(
        pos_df["as_of_date"],
        pos_df["quantity"],
        where="post",
        color="#ff7f0e",
        linewidth=1.6,
    )
    ax3.fill_between(
        pos_df["as_of_date"],
        pos_df["quantity"],
        step="post",
        alpha=0.3,
        color="#ff7f0e",
    )
    ax3.set_ylabel("Shares Held")
    ax3.set_xlabel("Date")
    ax3.grid(True, alpha=0.3)

    # Clean X-axis
    ax3.xaxis.set_major_locator(mdates.MonthLocator())
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax3.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO, interval=2))

    for ax in (ax1, ax2, ax3):
        ax.tick_params(axis="x", labelsize=9, rotation=30)
        ax.tick_params(axis="y", labelsize=9)

    plt.tight_layout()

    if output is None:
        output = (
            Path("/tmp")
            / f"{symbol}_twrr_chart_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )

    plt.savefig(output, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close()

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate enhanced symbol TWRR chart")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--annotate-trades", action="store_true")

    args = parser.parse_args()

    out = generate_symbol_chart(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        output=args.output,
        annotate_trades=args.annotate_trades,
    )
    print(f"Chart saved to: {out}")
