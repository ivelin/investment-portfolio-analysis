"""Lightweight CANSLIM scoring for portfolio positions.

This is a simplified version focused on the most actionable elements
for existing positions rather than full stock screening.
"""

from typing import Dict, Any, List


def score_canslim(
    symbol: str, realized_gains: List[Dict], current_position: Dict = None
) -> Dict[str, Any]:
    """
    Generate a lightweight CANSLIM-style score for a position.

    Scoring is intentionally conservative and focused on:
    - C: Current quarterly earnings (placeholder until we have fundamentals)
    - A: Annual earnings growth consistency
    - N: New highs / relative strength (inferred from trade frequency)
    - S: Supply/demand via volume and holding behavior
    - L: Leadership (inferred from profit consistency)
    - I: Institutional sponsorship (not available)
    - M: Market direction (not available here)

    Returns a dict with score (0-100) and qualitative assessment.
    """
    score = 50  # baseline
    factors = []

    # Profit consistency (proxy for earnings strength + leadership)
    if realized_gains:
        profits = [g.get("gain_loss", 0) or 0 for g in realized_gains]
        positive_trades = sum(1 for p in profits if p > 0)
        win_rate = positive_trades / len(profits) if profits else 0.5

        if win_rate > 0.7:
            score += 15
            factors.append("High win rate on realized trades")
        elif win_rate < 0.4:
            score -= 10
            factors.append("Low win rate - review entries")

        # Average profit per trade
        avg_profit = sum(profits) / len(profits)
        if avg_profit > 500:
            score += 10
            factors.append("Strong average profit per trade")

    # Holding behavior (proxy for supply/demand and discipline)
    if current_position:
        qty = current_position.get("quantity", 0) or 0
        if qty > 0:
            score += 5
            factors.append("Still holding - conviction present")
        else:
            score -= 5

    # Trade frequency (proxy for relative strength / new high behavior)
    if realized_gains and len(realized_gains) >= 3:
        score += 8
        factors.append("Multiple successful rounds - relative strength candidate")

    # Cap the score
    score = max(0, min(100, score))

    # Qualitative label
    if score >= 75:
        label = "Strong CANSLIM characteristics"
    elif score >= 60:
        label = "Solid - above average"
    elif score >= 45:
        label = "Average - monitor closely"
    else:
        label = "Weak - consider weeding"

    return {
        "canslim_score": round(score, 0),
        "canslim_label": label,
        "canslim_factors": factors[:4],  # top 4 most relevant
    }
