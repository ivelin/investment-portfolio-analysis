"""Technical analysis charts for private fund-as-symbol series."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from portfolio_analysis.paths import get_reports_dir

from .series import InsufficientFundHistory, load_fund_index_series
from .technicals import compute_ma_series


def generate_fund_ta_chart(
    series: Sequence[dict[str, Any]],
    *,
    fund_symbol: str,
    price_field: str = "liquidation_value",
    output_path: Path | str | None = None,
    title: str | None = None,
) -> Path:
    """Plot fund price series with EMA21 / SMA50 / SMA200 and a clear legend.

    ``price_field`` is typically ``liquidation_value`` (net liq as "price") or
    ``twrr_index`` (cash-flow-neutral performance). Missing MA windows are
    omitted from the plot (no invented history).

    Returns path to the written PNG.
    """
    if not series:
        raise InsufficientFundHistory(f"{fund_symbol}: no series to chart")

    ma = compute_ma_series(series, fund_symbol=fund_symbol, price_field=price_field)
    dates = pd.to_datetime(ma.as_of_dates)

    out = (
        Path(output_path)
        if output_path
        else _default_chart_path(fund_symbol, price_field)
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=120)
    price_label = (
        "Net liquidation value"
        if price_field == "liquidation_value"
        else "TWRR growth index (CF-neutral)"
    )
    ax.plot(dates, ma.prices, color="#1f77b4", linewidth=2.0, label=price_label)

    def _plot_ma(
        values: list[float | None], *, color: str, label: str, style: str
    ) -> None:
        ys = [v if v is not None else float("nan") for v in values]
        if all(v is None for v in values):
            return
        ax.plot(dates, ys, color=color, linewidth=1.4, linestyle=style, label=label)

    _plot_ma(ma.ema_21, color="#ff7f0e", label="21 EMA", style="-")
    _plot_ma(ma.sma_50, color="#2ca02c", label="50 DMA", style="--")
    _plot_ma(ma.sma_200, color="#d62728", label="200 DMA", style="-.")

    n = len(ma.prices)
    notes = []
    if n < 21:
        notes.append("EMA21 undefined (need ≥21 points)")
    if n < 50:
        notes.append("50 DMA undefined (need ≥50 points)")
    if n < 200:
        notes.append("200 DMA undefined (need ≥200 points)")

    chart_title = title or f"{fund_symbol} — {price_label}"
    ax.set_title(chart_title, fontsize=13, fontweight="bold")
    ax.set_xlabel("Date")
    ylabel = (
        "USD (net liq)" if price_field == "liquidation_value" else "Index (start=100)"
    )
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", framealpha=0.92)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()

    if notes:
        ax.text(
            0.01,
            0.02,
            " · ".join(notes),
            transform=ax.transAxes,
            fontsize=8,
            color="#555555",
            verticalalignment="bottom",
        )

    # Footnote: treat account as professionally managed fund symbol
    fig.text(
        0.5,
        0.01,
        "Private fund-as-symbol · no fabricated bars · deposits/withdrawals neutralized on TWRR index series",
        ha="center",
        fontsize=8,
        color="#666666",
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def generate_fund_ta_chart_from_db(
    conn,
    fund_symbol: str,
    *,
    price_field: str = "liquidation_value",
    output_path: Path | str | None = None,
) -> Path:
    """Load fund_daily from DB and chart it."""
    series = load_fund_index_series(conn, fund_symbol)
    return generate_fund_ta_chart(
        series,
        fund_symbol=fund_symbol,
        price_field=price_field,
        output_path=output_path,
    )


def _default_chart_path(fund_symbol: str, price_field: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in fund_symbol)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return get_reports_dir() / f"fund_ta_{safe}_{price_field}_{ts}.png"
