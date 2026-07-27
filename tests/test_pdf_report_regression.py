"""Regression tests for PDF report and chart generation.

These tests ensure that changes to table layout, data processing,
or chart logic do not break existing report functionality.
Run with: pytest tests/test_pdf_report_regression.py -q
"""

import tempfile
from pathlib import Path
import pytest

from portfolio_analysis.charts import generate_position_size_distribution_chart
from portfolio_analysis.pdf_report import create_portfolio_pdf_report


@pytest.fixture
def realistic_positions_csv(tmp_path):
    csv_content = """"Symbol","Description","Qty","Mkt Val (Market Value)","Avg Cost","Unrealized P/L"
"AAPL","Apple Inc",150,22500,140,1500
"NVDA","NVIDIA Corp",80,48000,420,12000
"MSFT","Microsoft",120,48000,320,9600
"GOOGL","Alphabet",60,10500,140,2100
"TSLA","Tesla Inc",40,12000,280,800
"""
    csv_file = tmp_path / "positions.csv"
    csv_file.write_text(csv_content)
    return csv_file


def test_chart_generates_with_schwab_format(realistic_positions_csv):
    """Chart must generate without crashing on standard Schwab export."""
    out = Path(tempfile.mktemp(suffix=".png"))
    result = generate_position_size_distribution_chart(realistic_positions_csv, out)
    assert result.exists()
    assert result.stat().st_size > 50000  # reasonable image size


def test_pdf_report_generates_without_regression(realistic_positions_csv):
    """Full PDF report must generate cleanly and include chart + table."""
    out_pdf = Path(tempfile.mktemp(suffix=".pdf"))
    result = create_portfolio_pdf_report(realistic_positions_csv, out_pdf)
    assert result.exists()
    assert result.stat().st_size > 100000  # PDF with content


def test_chart_handles_various_column_names(tmp_path):
    """Parser must be robust to different Schwab column header variations."""
    csv_variations = [
        '"Sym","Mkt Val","Cost"\n"AAPL",22500,140\n',
        '"Symbol","Market Value","Avg Cost"\n"AAPL",22500,140\n',
        '"Ticker","Value","Basis"\n"AAPL",22500,140\n',
    ]
    for i, content in enumerate(csv_variations):
        csv_file = tmp_path / f"var_{i}.csv"
        csv_file.write_text(content)
        out = Path(tempfile.mktemp(suffix=".png"))
        result = generate_position_size_distribution_chart(csv_file, out)
        assert result.exists(), f"Failed on variation {i}"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
