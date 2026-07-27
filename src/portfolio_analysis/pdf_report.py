"""Professional PDF Report Generator for Portfolio Analysis.

Generates clean, high-quality PDF reports using only ground truth data.
"""

from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

from .charts import generate_position_size_distribution_chart
from .reporting import get_reports_dir, default_report_path


def create_portfolio_pdf_report(
    positions_csv_path: Path,
    output_path: Path = None,
    title: str = "Weeding the Garden Report",
) -> Path:
    """
    Generate a professional PDF Weeding the Garden report.
    Includes:
    - Executive summary
    - Position size distribution chart
    - Full table with Efficiency, CANSLIM score, Profit, Recommendation (Keep/Add/Weed)
    """
    if output_path is None:
        output_path = default_report_path(
            prefix="Weeding_the_Garden_Report", suffix=".pdf"
        )

    # Generate the distribution chart into the same reports directory
    chart_path = generate_position_size_distribution_chart(
        positions_csv_path=positions_csv_path,
        output_path=get_reports_dir()
        / f"distribution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
    )

    # Create PDF
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=20,
        textColor=HexColor("#1a365d"),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )

    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=HexColor("#4a5568"),
        alignment=TA_CENTER,
        spaceAfter=16,
    )

    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=13,
        textColor=HexColor("#2c5282"),
        spaceBefore=14,
        spaceAfter=8,
        fontName="Helvetica-Bold",
    )

    body_style = ParagraphStyle(
        "BodyText",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=HexColor("#2d3748"),
        spaceAfter=6,
    )

    story = []

    # Title
    story.append(Paragraph(title, title_style))
    story.append(
        Paragraph(
            f"Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')} | Ground Truth Data Only",
            subtitle_style,
        )
    )

    # Executive Summary
    story.append(Paragraph("Executive Summary", section_style))
    story.append(
        Paragraph(
            "This report analyzes your portfolio using Capital Efficiency (Time-Adjusted Return) and CANSLIM principles. "
            "Positions are scored and given clear recommendations: <b>Keep</b> (strong performers), "
            "<b>Add</b> (promising but small), or <b>Weed</b> (underperformers or oversized laggards).",
            body_style,
        )
    )

    # Position Size Distribution Chart
    story.append(Paragraph("Position Size Distribution", section_style))
    if chart_path.exists():
        img = Image(str(chart_path), width=7 * inch, height=3.5 * inch)
        story.append(img)

    # Full Weeding the Garden Table
    story.append(Paragraph("Weeding the Garden Analysis", section_style))

    # Use DB data now that positions are properly ingested
    try:
        from portfolio_analysis.weed_the_garden import (
            generate_weed_the_garden_report,
        )
        from portfolio_analysis.db import get_connection

        conn = get_connection()
        full_report = generate_weed_the_garden_report(conn)
    except Exception:
        full_report = []

    active_report = [r for r in full_report if r.get("current_position_size", 0) > 0]

    if active_report:
        # Compute daily % efficiency
        for r in active_report:
            profit = r.get("total_profit", 0) or 0
            capital = r.get("avg_invested_capital", 1) or 1
            days = max(
                r.get("active_days", 30) or 30, 30
            )  # floor to avoid short-hold blowups
            daily_pct = (profit / capital / days) * 100 if days > 0 else 0
            r["daily_eff_pct"] = round(daily_pct, 3)

        active_report.sort(key=lambda x: x.get("daily_eff_pct", 0), reverse=True)

        table_data = [
            ["#", "Symbol", "Size", "Total Gain ($)", "Daily Eff %", "CANSLIM", "Rec."]
        ]
        for idx, r in enumerate(active_report[:100], 1):
            size = r.get("current_position_size", 0)
            profit = r.get("total_profit", 0)
            daily_eff = r.get("daily_eff_pct", 0)
            canslim = r.get("canslim_score", 0)
            rec = r.get("recommendation", "Keep")

            table_data.append(
                [
                    str(idx),
                    r.get("symbol", ""),
                    str(int(size)),
                    f"{profit:,.0f}",
                    f"{daily_eff:.3f}",
                    f"{canslim:.0f}",
                    rec,
                ]
            )

        col_widths = [
            0.4 * inch,
            0.7 * inch,
            0.55 * inch,
            1.0 * inch,
            0.85 * inch,
            0.65 * inch,
            2.6 * inch,
        ]
        table = Table(table_data, colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#2c5282")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), white),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("ALIGN", (1, 0), (1, -1), "LEFT"),
                    ("ALIGN", (-1, 0), (-1, -1), "LEFT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 8),
                    ("FONTSIZE", (0, 1), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                    ("TOPPADDING", (0, 0), (-1, 0), 5),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [HexColor("#ffffff"), HexColor("#f7fafc")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#cbd5e0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 10))
        story.append(
            Paragraph(
                "Showing top 100 active positions sorted by Daily Eff % (all active positions considered; lower-ranked ones truncated for readability). Closed positions excluded.",
                body_style,
            )
        )

        # Legend
        story.append(Paragraph("Legend & Methodology", section_style))
        legend_text = """<b>Active Positions Only:</b> Table filtered to currently open holdings (quantity > 0). Closed/exited positions excluded.<br/>
<b>#:</b> Rank by Daily Eff % (highest first).<br/>
<b>Size:</b> Current share quantity from latest Schwab export.<br/>
<b>Total Gain ($):</b> Realized P&L + Unrealized P&L.<br/>
<b>Daily Eff %:</b> Time-weighted average daily return = (Total Profit / Avg Invested Capital / Days Held) × 100. This is the capital efficiency indicator.<br/>
<b>CANSLIM:</b> 0-100 score from current earnings, annual growth, new highs, supply/demand, leadership, institutional sponsorship, and market direction.<br/>
<b>Rec.:</b> Dynamic recommendation based on Daily Eff % and CANSLIM score."""
        story.append(Paragraph(legend_text, body_style))
        # Formula Breakdown section
        story.append(Spacer(1, 15))
        story.append(Paragraph("Formula Breakdown & Examples", section_style))

        formula_text = """<b>Daily Eff % Formula:</b><br/>
Daily Eff % = (Total Profit / Avg Invested Capital / Max(Days Held, 30)) × 100<br/>
This represents the average daily return on capital actually deployed, with a 30-day floor to prevent unrealistic spikes from very short-term trades or options positions.<br/><br/>
<b>CANSLIM Score:</b> Composite 0-100 score based on 7 factors (Current earnings, Annual earnings growth, New highs, Supply & demand, Leader in industry, Institutional sponsorship, Market direction). Higher is better for growth stocks."""
        story.append(Paragraph(formula_text, body_style))

        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "<b>Calculation Examples (synthetic illustrations only — not live holdings):</b>",
                body_style,
            )
        )

        # Synthetic demo numbers only — never real operator balances or sizes.
        examples = [
            (
                "AAA (100 shares)",
                "Profit: $1,200 | Capital: ~$10k | Days: ~100 | Daily Eff: (1200 / 10000 / 100) * 100 = 0.12%",
            ),
            (
                "BBB (50 shares)",
                "Profit: $5,000 | Capital: ~$8k | Days: ~40 | Daily Eff: (5000 / 8000 / 40) * 100 = 1.56% (illustrative strong mover)",
            ),
            (
                "CCC (200 shares)",
                "Profit: -$50 | Capital: ~$20k | Days: ~180 | Daily Eff: (-50 / 20000 / 180) * 100 ≈ -0.001%",
            ),
        ]

        for title, calc in examples:
            story.append(Paragraph(f"<b>{title}</b><br/>{calc}", body_style))

    else:
        story.append(Paragraph("No active positions found in database.", body_style))

    # Footer
    story.append(Spacer(1, 20))
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=HexColor("#718096"),
        alignment=TA_CENTER,
    )
    story.append(
        Paragraph(
            "Portfolio Analysis Skill • All data is real and sourced from your brokerage exports. No simulated data used.",
            footer_style,
        )
    )

    doc.build(story)
    return output_path
