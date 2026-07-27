#!/usr/bin/env python3
"""
build_reconciled_daily_positions.py

Primary orchestration script for the Daily Position Reconstruction Engine.

Responsibilities:
- Ingest and reconcile exclusively from direct structured Schwab exports into gt_* tables (no PDF or SOTA VQA paths).
- Drive the granular daily position reconstruction.
- Run a set of headless evals (coverage, fidelity, consistency).
- Support a self-healing loop: reconcile → eval → correct → repeat until clean (or max iterations).
- Perform garbage collection of legacy/duplicate data.
- Produce clear reports and a "golden" daily positions table.

Usage examples:
    python tools/build_reconciled_daily_positions.py --help
    python tools/build_reconciled_daily_positions.py --sacred-dir ~/.investment-portfolio-analysis/schwab-exports --loop --max-iterations 5
"""

import argparse
from datetime import datetime
from pathlib import Path

from portfolio_analysis.db import create_schema, get_connection
import pandas as pd

from portfolio_analysis.daily_positions import (
    build_reconciled_daily_positions,
    reconstruct_daily_positions_for_symbol,
    persist_reconstructed_positions,
    evaluate_reconstruction,
    force_snap_to_gt_anchors,
    force_snap_relevant_anchors,
)
from portfolio_analysis.paths import broker_exports_dir, get_reports_dir
from portfolio_analysis.twrr import (
    populate_daily_twrr_from_subperiods,
    fill_daily_twrr_gaps,
    detect_twrr_inconsistencies,
    get_problematic_boundary_dates,
)


def main():
    parser = argparse.ArgumentParser(
        description="Build reconciled daily positions table"
    )
    parser.add_argument(
        "--sacred-dir",
        type=Path,
        default=broker_exports_dir("schwab"),
        help="Directory containing raw direct structured Schwab exports (CSV/XML/JSON)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Limit to specific symbols (default: all with anchors)",
    )
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--loop", action="store_true", help="Run reconciliation + eval loop until clean"
    )
    parser.add_argument(
        "--max-iterations", type=int, default=5, help="Safety cap for --loop mode"
    )
    parser.add_argument(
        "--verify-aapl",
        action="store_true",
        help="After run, print a quick AAPL sanity check",
    )

    args = parser.parse_args()

    conn = get_connection()
    create_schema(conn)

    print("=== Daily Position Reconstruction ===")
    print(f"Sacred dir: {args.sacred_dir}")
    print(f"Loop mode: {args.loop} (max iterations: {args.max_iterations})")

    # All GT data (gt_brokerage_statement_positions, gt_transactions, gt_realized_gains, etc.)
    # is assumed already ingested from direct structured exports via the canonical tools
    # (ingest_all_schwab_exports.py, ingest_account_statement_equities.py, etc.).
    # No SOTA JSON or PDF-derived data is loaded here.

    # Run the reconstruction for requested symbols
    symbols = [s.upper() for s in args.symbols] if args.symbols else None
    build_reconciled_daily_positions(
        conn, symbols=symbols, start_date=args.start_date, end_date=args.end_date
    )

    # 4. Demonstrate the self-healing loop (basic version)
    print("\n=== Self-Healing Reconciliation Loop (basic) ===")

    if symbols is None:
        symbols = [
            r["symbol"]
            for r in conn.execute(
                "SELECT DISTINCT symbol FROM gt_brokerage_statement_positions"
            ).fetchall()
        ]

    max_iter = args.max_iterations if args.loop else 1
    iteration_results = []

    for iteration in range(1, max_iter + 1):
        print(f"\n--- Iteration {iteration}/{max_iter} ---")

        total_issues = 0
        per_symbol_issues = {}

        for sym in symbols:
            # Reconstruct + persist (very conservative - only real event dates + prices)
            df = reconstruct_daily_positions_for_symbol(
                conn, sym, args.start_date, args.end_date
            )
            inserted = persist_reconstructed_positions(conn, df)

            # Use the new anchored Journal-safe reconstruction for the continuous daily series
            # (this is the fix for the previously incorrectly derived rows in daily_position_values,
            # e.g. 3x spikes on 2026-05-22 Journal batch). ensure_daily... will use the safe
            # get_position_quantity_on_date (gt_daily anchor + post-tx, Journals skipped).
            try:
                from portfolio_analysis.market_data import ensure_daily_market_values

                clean_start = args.start_date or "2025-01-01"
                clean_end = args.end_date or datetime.now().strftime("%Y-%m-%d")
                # First ensure we have the GT anchors snapped (high quality)
                force_snap_to_gt_anchors(conn, sym)
                ensured = ensure_daily_market_values(conn, sym, clean_start, clean_end)
                if ensured:
                    print(
                        f"    [new-recon] ensured {ensured} clean daily position rows for {sym} (Journal-safe)"
                    )
            except Exception as e:
                print(f"    [new-recon] note for {sym}: {e}")

            # Daily reconstruction eval (strict pristine criteria)
            daily_eval = evaluate_reconstruction(
                conn, sym, args.start_date, args.end_date
            )

            # TWRR inconsistency eval (the original pain point the user reported)
            twrr_issues = detect_twrr_inconsistencies(sym, conn=conn)
            twrr_issue_count = len(twrr_issues)

            issues = 0
            if not daily_eval.get("is_pristine", False):
                issues += 1
            issues += twrr_issue_count

            print(
                f"  {sym}: {inserted} rows | Pristine: {daily_eval.get('is_pristine')} | TWRR issues: {twrr_issue_count}"
            )

            total_issues += issues
            per_symbol_issues[sym] = issues

            # Correction step (the heart of the self-healing loop):
            # Prefer targeted snapping using the exact problematic TWRR boundary dates.
            if issues > 0:
                problematic_dates = get_problematic_boundary_dates(sym, conn=conn)
                if problematic_dates:
                    snapped = force_snap_relevant_anchors(conn, sym, problematic_dates)
                    print(
                        f"    → Targeted correction: Snapped {snapped} relevant GT anchors near problematic dates for {sym}"
                    )
                else:
                    snapped = force_snap_to_gt_anchors(conn, sym)
                    print(
                        f"    → Correction applied: Force-snapped {snapped} GT anchors for {sym}"
                    )

        # Simple garbage collection: remove low-quality interpolated rows for symbols that are now pristine
        if total_issues == 0:
            for sym in symbols:
                conn.execute(
                    """
                    DELETE FROM daily_position_values
                    WHERE symbol = ? AND data_quality < 70 AND price_source LIKE '%derived%'
                """,
                    (sym,),
                )
            conn.commit()
            print(
                "  [Garbage Collection] Removed low-quality interpolated rows for clean symbols."
            )

        iteration_results.append(
            {
                "iteration": iteration,
                "total_issues": total_issues,
                "per_symbol": per_symbol_issues,
            }
        )

        # Stop only when everything is pristine (no daily issues + no TWRR issues)
        all_pristine = all(
            evaluate_reconstruction(conn, sym, args.start_date, args.end_date).get(
                "is_pristine", False
            )
            for sym in symbols
        )
        if total_issues == 0 and all_pristine:
            print(
                "\n✓✓✓ Daily position data is now PRISTINE across all symbols. No further inconsistencies."
            )
            break
        else:
            print(
                f"\n  {total_issues} issue(s) found. Corrections + GC applied. Re-running..."
            )

    # Final Summary
    print("\n" + "=" * 60)
    print("RECONCILIATION LOOP SUMMARY")
    print("=" * 60)
    print(f"Total iterations run: {len(iteration_results)}")
    for res in iteration_results:
        print(f"  Iteration {res['iteration']}: {res['total_issues']} total issues")
        for sym, cnt in res["per_symbol"].items():
            if cnt > 0:
                print(f"    - {sym}: {cnt} issues")
    print("=" * 60)

    if iteration_results and iteration_results[-1]["total_issues"] == 0:
        print("✓ Loop exited cleanly with zero inconsistencies.")
    else:
        print("! Loop finished with remaining issues (see details above).")

    # Write a final "Pristine Reconciliation Report" artifact (single fixed filename, user-preferred style)
    report_dir = get_reports_dir()
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / "Daily_Positions_Pristine_Report.txt"

    with open(report_file, "w") as f:
        f.write("Daily Position Reconstruction - Pristine Report\n")
        f.write("=" * 65 + "\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Total iterations run: {len(iteration_results)}\n\n")

        for res in iteration_results:
            f.write(
                f"Iteration {res['iteration']}: {res['total_issues']} total issues\n"
            )
            for sym, cnt in res["per_symbol"].items():
                if cnt > 0:
                    f.write(f"  - {sym}: {cnt} issues\n")
            f.write("\n")

        if iteration_results and iteration_results[-1]["total_issues"] == 0:
            f.write("✓✓✓ FINAL STATUS: PRISTINE\n")
            f.write(
                "All symbols meet the strict pristine criteria (≥90% high-quality real-source rows, ≤5% low-quality interpolation, zero TWRR inconsistencies).\n"
            )
        else:
            f.write("! FINAL STATUS: Some issues remain after max iterations.\n")

    print(f"\n=== Pristine Report written to {report_file} ===")

    # Always populate daily_twrr using the canonical subperiod logic + gapfill + validation.
    # This ensures reports have data and enforces the DRY/MECE single source of truth.
    # The verify_aapl is kept for extra debug output.
    print(
        "\n=== Populating daily_twrr (boundary + gapfill with boundary consistency validation) ==="
    )
    for sym in symbols or (["AAPL"] if args.verify_aapl else []):
        try:
            n = populate_daily_twrr_from_subperiods(conn, sym)
            print(f"  {sym}: {n} boundary rows")

            gap_inserted = fill_daily_twrr_gaps(conn, sym)
            print(f"       {gap_inserted} gap-filled days (with cross-path validation)")

            if args.verify_aapl:
                preview = pd.read_sql(
                    "SELECT as_of_date, daily_return, is_subperiod_boundary, calc_version FROM daily_twrr WHERE symbol=? ORDER BY as_of_date DESC LIMIT 5",
                    conn,
                    params=(sym,),
                )
                print(preview.to_string(index=False))
        except Exception as e:
            print(f"  (skipped for {sym}: {e})")

    if args.verify_aapl:
        print("\n=== Quick AAPL Verification ===")
        df = reconstruct_daily_positions_for_symbol(conn, "AAPL")
        print(f"AAPL reconstructed rows: {len(df)}")
        if not df.empty:
            print(df.head(3))
            print("...")
            print(df.tail(3))

    print("\n=== Run complete ===")
    print(f"Review the full Pristine Report at: {report_file}")


if __name__ == "__main__":
    main()
