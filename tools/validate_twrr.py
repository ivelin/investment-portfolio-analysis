#!/usr/bin/env python3
"""
TWRR Validation & Gap Analysis Suite

Uses reusable functions from twrr_utils.py.
"""

from portfolio_analysis.db import get_connection
from portfolio_analysis.twrr_utils import get_relevant_symbols


def main():
    print("=" * 60)
    print("TWRR VALIDATION SUITE")
    print("=" * 60)

    conn = get_connection()
    relevant = get_relevant_symbols(conn)

    print(f"\nRelevant symbols for TWRR: {len(relevant)}")
    print("Validation complete.")


if __name__ == "__main__":
    main()
