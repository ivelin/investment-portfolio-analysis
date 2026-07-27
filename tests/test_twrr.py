"""
Regression tests for the new real Daily TWRR Capital Efficiency system.

These tests ensure we never regress to the old broken heuristic
and that all calculations only use credible data sources.
"""

from pathlib import Path
import tempfile

from portfolio_analysis.db import init_db
from portfolio_analysis.twrr import get_capital_efficiency_twrr_report


def test_twrr_returns_empty_when_no_real_data():
    """When there is no credible daily position data, twrr should not invent numbers."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        conn = init_db(db_path)

        # No daily_position_values at all
        result = get_capital_efficiency_twrr_report(conn=conn, only_active=True)
        assert result == [], "Should return empty list when no real daily data exists"


# Future tests will be added here as we implement:
# - test that yfinance / Massive data is correctly tagged with price_source
# - test caching behavior in market_price_bars
# - test that TWRR numbers are reasonable on synthetic data
# - test that ensure_real_data triggers population correctly
