"""Alert evaluation for private fund symbols (TWRR index technicals)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from .series import InsufficientFundHistory
from .technicals import FundMovingAverages, compute_fund_moving_averages


@dataclass(frozen=True)
class FundAlert:
    rule: str
    fired: bool
    message: str
    as_of_date: str
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_fund_alerts(
    series: Sequence[dict[str, Any]],
    *,
    fund_symbol: str,
) -> list[FundAlert]:
    """Evaluate under-MA and stack-broken rules on the fund TWRR index."""
    try:
        mas = compute_fund_moving_averages(series, fund_symbol=fund_symbol)
    except InsufficientFundHistory as exc:
        return [
            FundAlert(
                rule="insufficient_history",
                fired=True,
                message=str(exc),
                as_of_date="",
                detail={"points": len(series)},
            )
        ]

    return _alerts_from_mas(mas)


def _alerts_from_mas(mas: FundMovingAverages) -> list[FundAlert]:
    alerts: list[FundAlert] = []
    px = mas.twrr_index
    d = mas.as_of_date

    def under(rule: str, ma: float | None, label: str) -> None:
        if ma is None:
            alerts.append(
                FundAlert(
                    rule=f"{rule}_unavailable",
                    fired=False,
                    message=f"Insufficient history for {label}",
                    as_of_date=d,
                    detail={"points": mas.points, "twrr_index": px},
                )
            )
            return
        fired = px < ma
        alerts.append(
            FundAlert(
                rule=rule,
                fired=fired,
                message=(
                    f"Index {px:.4f} is below {label} {ma:.4f}"
                    if fired
                    else f"Index {px:.4f} is at/above {label} {ma:.4f}"
                ),
                as_of_date=d,
                detail={"twrr_index": px, "ma": ma, "points": mas.points},
            )
        )

    under("below_ema_21", mas.ema_21, "EMA21")
    under("below_sma_50", mas.sma_50, "SMA50")
    under("below_sma_200", mas.sma_200, "SMA200")

    if mas.bullish_stack is None:
        alerts.append(
            FundAlert(
                rule="ma_stack_unavailable",
                fired=False,
                message="Need EMA21, SMA50, and SMA200 to evaluate stack",
                as_of_date=d,
                detail=mas.as_dict(),
            )
        )
    else:
        broken = not mas.bullish_stack
        alerts.append(
            FundAlert(
                rule="ma_stack_broken",
                fired=broken,
                message=(
                    "MA stack not bullish (want EMA21 > SMA50 > SMA200)"
                    if broken
                    else "MA stack bullish (EMA21 > SMA50 > SMA200)"
                ),
                as_of_date=d,
                detail={
                    "ema_21": mas.ema_21,
                    "sma_50": mas.sma_50,
                    "sma_200": mas.sma_200,
                    "bullish_stack": mas.bullish_stack,
                },
            )
        )

    return alerts
