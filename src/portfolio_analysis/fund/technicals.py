"""Moving averages on fund series (TWRR index and/or net liquidation value)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import pandas as pd

from .series import InsufficientFundHistory


@dataclass(frozen=True)
class FundMovingAverages:
    fund_symbol: str
    as_of_date: str
    price: float
    price_field: str
    ema_21: float | None
    sma_50: float | None
    sma_200: float | None
    points: int
    bullish_stack: bool | None  # None if any MA missing
    # Back-compat alias used by alerts
    twrr_index: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "fund_symbol": self.fund_symbol,
            "as_of_date": self.as_of_date,
            "price": self.price,
            "price_field": self.price_field,
            "twrr_index": self.twrr_index,
            "ema_21": self.ema_21,
            "sma_50": self.sma_50,
            "sma_200": self.sma_200,
            "points": self.points,
            "bullish_stack": self.bullish_stack,
        }


@dataclass(frozen=True)
class FundMaSeries:
    """Full date-aligned MA series for charting (None where window not filled)."""

    fund_symbol: str
    price_field: str
    as_of_dates: list[str]
    prices: list[float]
    ema_21: list[float | None]
    sma_50: list[float | None]
    sma_200: list[float | None]


def compute_fund_moving_averages(
    series: Sequence[dict[str, Any]],
    *,
    fund_symbol: str,
    min_points: int = 2,
    price_field: str = "twrr_index",
) -> FundMovingAverages:
    """Compute EMA21 / SMA50 / SMA200 on ``price_field`` (default twrr_index).

    Raises InsufficientFundHistory if the series is empty or shorter than min_points.
    Individual MAs are None when history is shorter than their window.
    """
    if len(series) < min_points:
        raise InsufficientFundHistory(
            f"{fund_symbol}: need at least {min_points} fund_daily points, have {len(series)}"
        )

    frame = pd.DataFrame(list(series))
    if price_field not in frame.columns or "as_of_date" not in frame.columns:
        raise ValueError(f"series rows must include as_of_date and {price_field}")

    idx = frame[price_field].astype(float)
    ema_21 = _last_or_none(idx.ewm(span=21, adjust=False).mean(), need=21, n=len(idx))
    sma_50 = _last_or_none(
        idx.rolling(window=50, min_periods=50).mean(), need=50, n=len(idx)
    )
    sma_200 = _last_or_none(
        idx.rolling(window=200, min_periods=200).mean(), need=200, n=len(idx)
    )

    last = frame.iloc[-1]
    last_px = float(last[price_field])
    bullish: bool | None
    if ema_21 is None or sma_50 is None or sma_200 is None:
        bullish = None
    else:
        bullish = ema_21 > sma_50 > sma_200

    # twrr_index field for alerts back-compat: use actual twrr when present else price
    twrr_px = float(last["twrr_index"]) if "twrr_index" in frame.columns else last_px

    return FundMovingAverages(
        fund_symbol=fund_symbol,
        as_of_date=str(last["as_of_date"]),
        price=last_px,
        price_field=price_field,
        ema_21=ema_21,
        sma_50=sma_50,
        sma_200=sma_200,
        points=len(frame),
        bullish_stack=bullish,
        twrr_index=twrr_px,
    )


def compute_ma_series(
    series: Sequence[dict[str, Any]],
    *,
    fund_symbol: str,
    price_field: str = "liquidation_value",
) -> FundMaSeries:
    """Full MA curves for charting (None until each window is fully defined)."""
    if not series:
        raise InsufficientFundHistory(f"{fund_symbol}: empty series")
    frame = pd.DataFrame(list(series))
    if price_field not in frame.columns or "as_of_date" not in frame.columns:
        raise ValueError(f"series rows must include as_of_date and {price_field}")
    prices = frame[price_field].astype(float)
    dates = [str(d) for d in frame["as_of_date"].tolist()]
    ema = prices.ewm(span=21, adjust=False).mean()
    sma50 = prices.rolling(window=50, min_periods=50).mean()
    sma200 = prices.rolling(window=200, min_periods=200).mean()

    def _series_or_none(s: pd.Series, need: int) -> list[float | None]:
        out: list[float | None] = []
        for i, val in enumerate(s.tolist()):
            if i + 1 < need or pd.isna(val):
                out.append(None)
            else:
                out.append(float(val))
        return out

    return FundMaSeries(
        fund_symbol=fund_symbol,
        price_field=price_field,
        as_of_dates=dates,
        prices=[float(x) for x in prices.tolist()],
        ema_21=_series_or_none(ema, 21),
        sma_50=_series_or_none(sma50, 50),
        sma_200=_series_or_none(sma200, 200),
    )


def _last_or_none(series: pd.Series, *, need: int, n: int) -> float | None:
    if n < need:
        return None
    val = series.iloc[-1]
    if pd.isna(val):
        return None
    return float(val)
