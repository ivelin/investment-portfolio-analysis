#!/usr/bin/env python3
"""
Extract Positions table from Schwab/TDA brokerage statement PDF to CSV.

Usage:
    python tools/extract_positions_to_csv.py "Brokerage Statement_2026-04-30_052.PDF" --output fix_positions.csv
"""

import argparse
import csv
from pathlib import Path
import pdfplumber
import sys


def extract_positions_to_csv(pdf_path: Path, output_csv: Path):
    positions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if "Account Positions" not in text and "Positions" not in text:
                continue

            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                header = [str(c).strip().lower() if c else "" for c in table[0]]

                symbol_idx = next(
                    (
                        i
                        for i, h in enumerate(header)
                        if "symbol" in h or "description" in h
                    ),
                    None,
                )
                qty_idx = next(
                    (i for i, h in enumerate(header) if "quantity" in h), None
                )

                if symbol_idx is None or qty_idx is None:
                    continue

                for row in table[1:]:
                    if not row or not row[symbol_idx]:
                        continue

                    symbol = str(row[symbol_idx]).split()[0].strip().upper()
                    if (
                        not symbol
                        or len(symbol) > 12
                        or symbol in {"STOCKS", "MUTUAL", "FUNDS", "CASH"}
                    ):
                        continue

                    try:
                        qty = (
                            float(str(row[qty_idx]).replace(",", "").replace("$", ""))
                            if row[qty_idx]
                            else 0
                        )
                    except Exception:
                        qty = 0

                    if qty == 0:
                        continue

                    price = None
                    value = None
                    cost = None

                    for i, h in enumerate(header):
                        val = row[i]
                        if "price" in h:
                            try:
                                price = float(
                                    str(val).replace(",", "").replace("$", "")
                                )
                            except Exception:
                                pass
                        if "value" in h or "market value" in h:
                            try:
                                value = float(
                                    str(val).replace(",", "").replace("$", "")
                                )
                            except Exception:
                                pass
                        if "cost" in h and "basis" in h:
                            try:
                                cost = float(str(val).replace(",", "").replace("$", ""))
                            except Exception:
                                pass

                    positions.append(
                        {
                            "symbol": symbol,
                            "quantity": qty,
                            "market_price": price,
                            "market_value": value,
                            "cost_basis": cost,
                            "page": page_num,
                        }
                    )

    if not positions:
        print(f"No positions found in {pdf_path.name}")
        return 0

    # Write CSV
    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "quantity",
                "market_price",
                "market_value",
                "cost_basis",
                "page",
            ],
        )
        writer.writeheader()
        writer.writerows(positions)

    print(f"Extracted {len(positions)} positions → {output_csv}")
    return len(positions)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="Path to Schwab brokerage statement PDF")
    parser.add_argument("--output", "-o", help="Output CSV path")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    output = (
        Path(args.output) if args.output else pdf_path.with_suffix(".positions.csv")
    )
    extract_positions_to_csv(pdf_path, output)
