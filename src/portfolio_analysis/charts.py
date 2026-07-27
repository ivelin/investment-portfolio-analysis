"""Portfolio visualization charts.

This module contains reusable, high-quality charting functions
for portfolio analysis reports.
"""

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
import matplotlib.pyplot as plt

from .reporting import get_reports_dir

matplotlib.use("Agg")


def _read_schwab_positions(csv_path):
    """Robust reader for real Schwab positions exports (handles title row + blank line)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        lines = f.readlines()

    # Skip title row and possible blank row
    start = 0
    for i, line in enumerate(lines[:3]):
        if "Symbol" in line or "Mkt Val" in line:
            start = i
            break
    if start == 0 and len(lines) > 2:
        start = 2  # common Schwab format: title, blank, header

    return csv.DictReader(lines[start:])


def generate_position_size_distribution_chart(
    positions_csv_path: Path,
    output_path: Path = None,
    title: str = "Portfolio Position Size Distribution",
) -> Path:
    """
    Generate a professional dual-axis position size distribution chart.

    - Bars: Percentage of total portfolio value
    - Line + markers: Number of positions in each bucket
    - Returns the path to the saved PNG image.
    """
    if output_path is None:
        output_path = get_reports_dir() / "portfolio_distribution_dual.png"

    bucket_ranges = [
        (0, 1000),
        (1000, 2000),
        (2000, 3000),
        (3000, 5000),
        (5000, 7500),
        (7500, 10000),
        (10000, 15000),
        (15000, 25000),
        (25000, 40000),
        (40000, 60000),
        (60000, 100000),
        (100000, 200000),
        (200000, float("inf")),
    ]

    bucket_values = defaultdict(float)
    bucket_counts = defaultdict(int)
    total_value = 0.0

    with open(positions_csv_path, newline="", encoding="utf-8") as f:
        lines = f.readlines()

    if len(lines) < 2:
        raise ValueError("Positions file appears to be empty or invalid.")

    headers = [h.strip('"').lower() for h in lines[0].strip().split('","')]
    mkt_val_idx = None
    possible_names = ["mkt val", "market value", "mktval", "value", "marketvalue"]
    for i, h in enumerate(headers):
        if any(name in h for name in possible_names):
            mkt_val_idx = i
            break
    if mkt_val_idx is None:
        mkt_val_idx = 7  # fallback for Schwab exports

    for line in lines[1:]:
        if not line.strip():
            continue
        fields = [f.strip('"') for f in line.strip().split('","')]
        if len(fields) <= mkt_val_idx:
            continue
        try:
            mkt_val = float(fields[mkt_val_idx].replace("$", "").replace(",", ""))
        except (ValueError, IndexError):
            continue
        if mkt_val <= 0:
            continue

        total_value += mkt_val
        for low, high in bucket_ranges:
            if low <= mkt_val < high:
                bucket_values[(low, high)] += mkt_val
                bucket_counts[(low, high)] += 1
                break

    # Prepare plot data
    labels = []
    value_pcts = []
    counts = []
    for low, high in bucket_ranges:
        val = bucket_values[(low, high)]
        value_pcts.append(val / total_value * 100 if total_value > 0 else 0)
        counts.append(bucket_counts[(low, high)])

        if high == float("inf"):
            labels.append(f">${low / 1000:.0f}k+")
        else:
            labels.append(f"${low / 1000:.0f}k–${high / 1000:.0f}k")

    # Create dual-axis chart
    fig, ax1 = plt.subplots(figsize=(15, 8))

    colors = [
        "#2E86AB" if v < 5 else "#A23B72" if v < 20 else "#F18F01" for v in value_pcts
    ]
    bars = ax1.bar(
        labels,
        value_pcts,
        color=colors,
        edgecolor="white",
        linewidth=1.5,
        alpha=0.92,
        label="% of Portfolio Value",
    )

    ax1.set_ylabel("% of Total Portfolio Value", fontsize=13, color="#2E86AB")
    ax1.tick_params(axis="y", labelcolor="#2E86AB")
    ax1.set_ylim(0, max(max(value_pcts) * 1.28, 5))
    ax1.spines["top"].set_visible(False)

    # Value labels on bars
    for bar, val in zip(bars, value_pcts):
        if val > 0.8:
            ax1.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1.1,
                f"{val:.1f}%",
                ha="center",
                va="bottom",
                fontsize=11,
                fontweight="bold",
                color="#2E86AB",
            )

    # Right axis - Position Count
    ax2 = ax1.twinx()
    ax2.plot(
        labels,
        counts,
        color="#E63946",
        marker="o",
        linewidth=3.2,
        markersize=9.5,
        markerfacecolor="white",
        markeredgewidth=2.8,
        label="Number of Positions",
    )
    ax2.set_ylabel("Number of Positions", fontsize=13, color="#E63946")
    ax2.tick_params(axis="y", labelcolor="#E63946")
    ax2.set_ylim(0, max(max(counts) * 1.35, 5))

    # Count labels
    for i, (x, y) in enumerate(zip(labels, counts)):
        ax2.annotate(
            str(y),
            (x, y),
            textcoords="offset points",
            xytext=(0, 13),
            ha="center",
            fontsize=11,
            fontweight="bold",
            color="#E63946",
        )

    ax1.set_xlabel("Position Size Bucket", fontsize=13)
    ax1.set_title(
        f"{title}\n(Value % vs Number of Positions)",
        fontsize=17,
        fontweight="bold",
        pad=22,
    )

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        lines1 + lines2,
        labels1 + labels2,
        loc="upper right",
        framealpha=0.95,
        fontsize=11,
    )

    ax1.grid(axis="y", alpha=0.22, linestyle="--")
    plt.xticks(rotation=42, ha="right", fontsize=10.5)
    plt.tight_layout()

    plt.savefig(output_path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close()

    return output_path


def generate_twrr_ohlc_position_chart(
    symbol: str,
    output_path: Optional[Path] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    title: Optional[str] = None,
) -> Path:
    """
    Generate a dual/triple panel chart for a symbol:

    - Panel 1 (top): Cumulative TWRR (from daily_twrr) or simple close price proxy
    - Panel 2 (middle): OHLC bars (or close price line) from price cache
    - Panel 3 (bottom): Position size as clean step function

    The bottom panel uses the new anchored reconstruction (via reporting helper)
    instead of querying daily_position_values (Journal-inflated spikes) or gt_daily_positions (sparse)
    directly. Journals are filtered in the recon.

    This is the chart generator updated per the position reconstruction fix.
    """
    import matplotlib.pyplot as plt
    import pandas as pd

    from .db import get_connection
    from .market_data import fetch_historical_prices
    from .reporting import get_daily_position_series_for_symbol

    if output_path is None:
        output_path = (
            get_reports_dir()
            / f"{symbol}_twrr_ohlc_pos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        )

    conn = get_connection()

    # Position series (the key: use recon, not raw tables)
    pos_df = get_daily_position_series_for_symbol(
        symbol, start_date, end_date, conn=conn
    )
    if pos_df.empty:
        pos_df = pd.DataFrame({"as_of_date": [], "quantity": []})

    # Prices for OHLC / price panel
    p_start = start_date or (
        pos_df["as_of_date"].min() if not pos_df.empty else "2026-01-01"
    )
    p_end = end_date or (
        pos_df["as_of_date"].max()
        if not pos_df.empty
        else datetime.now().strftime("%Y-%m-%d")
    )
    price_df = pd.DataFrame()
    try:
        price_df = fetch_historical_prices(
            [symbol], p_start, p_end, provider="auto", use_cache=True
        )
    except Exception:
        pass

    # TWRR / cumulative from daily_twrr if available (fast path)
    twrr_df = pd.DataFrame()
    try:
        twrr_rows = conn.execute(
            """
            SELECT as_of_date, daily_return
            FROM daily_twrr
            WHERE symbol = ? AND as_of_date BETWEEN ? AND ?
            ORDER BY as_of_date
            """,
            (symbol, p_start, p_end),
        ).fetchall()
        if twrr_rows:
            twrr_df = pd.DataFrame(
                [(r[0], r[1] or 0.0) for r in twrr_rows],
                columns=["as_of_date", "daily_return"],
            )
            twrr_df["cum_twrr"] = (1 + twrr_df["daily_return"]).cumprod() - 1
    except Exception:
        pass

    # Plot
    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(12, 9), sharex=True, gridspec_kw={"height_ratios": [1, 1.2, 0.8]}
    )

    # Top: TWRR cum (or fallback note)
    if not twrr_df.empty:
        ax1.plot(
            twrr_df["as_of_date"],
            twrr_df["cum_twrr"] * 100,
            color="#1f77b4",
            linewidth=1.8,
            label="Cumulative TWRR %",
        )
        ax1.axhline(0, color="gray", linewidth=0.5, linestyle="--")
        ax1.set_ylabel("Cumul. TWRR %")
        ax1.legend(loc="upper left", fontsize=8)
    else:
        ax1.text(
            0.5,
            0.5,
            "TWRR (daily_twrr) not populated for window\n(run recon)",
            ha="center",
            va="center",
            transform=ax1.transAxes,
        )
        ax1.set_ylabel("Cumul. TWRR %")

    ax1.set_title(
        title or f"{symbol} — TWRR / Price / Position Size (anchored recon)",
        fontsize=12,
        fontweight="bold",
    )
    ax1.grid(True, alpha=0.3)

    # Middle: price line (OHLC lite)
    if not price_df.empty and symbol in price_df.columns:
        ax2.plot(
            price_df.index.astype(str),
            price_df[symbol],
            color="#2ca02c",
            linewidth=1.2,
            label="Close",
        )
        ax2.set_ylabel(f"{symbol} Price")
        ax2.legend(loc="upper left", fontsize=8)
    else:
        ax2.text(
            0.5,
            0.5,
            "No price data in cache for window",
            ha="center",
            va="center",
            transform=ax2.transAxes,
        )
        ax2.set_ylabel("Price")
    ax2.grid(True, alpha=0.3)

    # Bottom: position size STEP (clean from recon)
    if not pos_df.empty:
        # step plot for qty
        ax3.step(
            pos_df["as_of_date"],
            pos_df["quantity"],
            where="post",
            color="#d62728",
            linewidth=1.8,
            label="Position (shares)",
        )
        ax3.fill_between(
            pos_df["as_of_date"],
            pos_df["quantity"],
            step="post",
            alpha=0.15,
            color="#d62728",
        )
        ax3.set_ylabel("Shares Held")
        ax3.set_xlabel("Date")
        ax3.legend(loc="upper left", fontsize=8)
    else:
        ax3.text(
            0.5,
            0.5,
            "No position data",
            ha="center",
            va="center",
            transform=ax3.transAxes,
        )
        ax3.set_ylabel("Shares Held")
        ax3.set_xlabel("Date")
    ax3.grid(True, alpha=0.3)

    # rotate dates on bottom
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45, ha="right", fontsize=8)
    for ax in (ax1, ax2, ax3):
        ax.tick_params(axis="x", labelsize=7)
        ax.tick_params(axis="y", labelsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close()

    return output_path
