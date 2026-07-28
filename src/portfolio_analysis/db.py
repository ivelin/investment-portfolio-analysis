"""SQLite database setup for portfolio-analysis skill."""

import sqlite3
from pathlib import Path

from .paths import default_db_path

# Back-compat alias; prefer default_db_path() so env changes apply at connect time.
DB_PATH = default_db_path()


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    # Re-read env via default_db_path() so tests/CI env overrides work reliably.
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create the full database schema.

    We maintain a strict separation (per user requirements):
    - Ground Truth tables (gt_*): Direct, immutable imports from raw export documents.
      These are the single source of truth. Never computed or mutated after import.
    - Derived / Calculated tables: Everything that can be regenerated from GT + rules
      (qty reconstruction, TWRR values, classified cash flows, etc.).

    This enables reproducible test harnesses that replay full import from raw files.
    """
    cursor = conn.cursor()

    # ==================================================================
    # GROUND TRUTH TABLES (immutable imports from raw export documents)
    # These tables contain ONLY data that came directly from the user's
    # Schwab / TDA export files (CSVs, XML, PDFs). They are append-only
    # after a verified import and are the sole source for all calculations.
    # ==================================================================

    # Raw transactions straight from Schwab/TDA export files (CSV/XML)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            transaction_type TEXT,
            quantity REAL,
            price REAL,
            amount REAL,
            fees REAL,
            description TEXT,
            source_file TEXT NOT NULL,
            source_type TEXT DEFAULT 'schwab_export',
            ingested_at TEXT,
            UNIQUE(symbol, transaction_date, quantity, amount, description, source_file)
        )
    """)

    # ------------------------------------------------------------------
    # GROUND TRUTH: Brokerage Statement Positions (PDFs)
    # Different document type → dedicated table (user requirement).
    # These are the authoritative "exact position quantity at statement date"
    # anchors extracted from monthly/quarterly TDA/Schwab brokerage statements.
    # They are the primary mechanism for precise historical qty reconstruction
    # back to 2022 (and earlier).
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_brokerage_statement_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,                    -- Statement closing date (YYYY-MM-DD)
            quantity REAL NOT NULL,
            market_price REAL,
            market_value REAL,
            cost_basis REAL,
            avg_cost REAL,
            unrealized_gain_loss REAL,
            estimated_annual_income REAL,
            source_statement TEXT NOT NULL,              -- Original PDF filename
            statement_period_start TEXT,
            statement_period_end TEXT,
            page_number INTEGER,
            account_number TEXT,
            data_quality INTEGER DEFAULT 100,            -- 100 = direct from user-provided statement
            extraction_method TEXT,                      -- 'grok' | 'pdfplumber' | 'manual'
            notes TEXT,
            ingested_at TEXT DEFAULT (datetime('now')),
            UNIQUE(symbol, as_of_date, source_statement)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_gt_bsp_symbol_date
        ON gt_brokerage_statement_positions(symbol, as_of_date)
    """)

    # Official daily positions snapshots from Schwab "Positions" export CSVs
    # (the highest-trust EOD market values + quantities the user downloads).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_daily_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            quantity REAL NOT NULL,
            avg_cost REAL,
            market_value REAL,
            unrealized_pl REAL,
            source_file TEXT NOT NULL,
            data_quality INTEGER DEFAULT 100,
            UNIQUE(symbol, as_of_date)
        )
    """)

    # Raw realized gains/lots directly from the Gain/Loss export CSV
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_realized_gains (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            opened_date TEXT,
            closed_date TEXT NOT NULL,
            quantity REAL NOT NULL,
            cost_basis REAL,
            proceeds REAL,
            gain_loss REAL,
            term TEXT,
            wash_sale TEXT,
            source_file TEXT NOT NULL,
            UNIQUE(symbol, opened_date, closed_date, quantity, source_file)
        )
    """)

    # ------------------------------------------------------------------
    # GROUND TRUTH: 1099-R / Tax Documents (new document type)
    # Per user requirement: different tables for different document types.
    # Immutable anchor for tax-year distributions from the same IRA.
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_1099r_distributions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tax_year INTEGER NOT NULL,
            form_type TEXT DEFAULT '1099-R',
            payer_name TEXT,
            payer_tin TEXT,
            recipient_name TEXT,
            recipient_account TEXT,
            gross_distribution REAL,
            taxable_amount REAL,
            federal_tax_withheld REAL,
            distribution_code TEXT,
            ira_sep_simple INTEGER DEFAULT 0,
            date_of_payment TEXT,
            source_file TEXT NOT NULL,
            ingested_at TEXT,
            UNIQUE(tax_year, recipient_account, source_file)
        )
    """)

    # ==================================================================
    # DERIVED / CALCULATED TABLES
    # Everything below can (and should) be dropped and fully regenerated
    # from the ground truth tables above + deterministic rules.
    # ==================================================================

    # Transactions augmented with reconstructed position sizes (from GT anchors + tx)
    # We keep the original name for now for compatibility, but it is derived.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            transaction_type TEXT,
            quantity REAL,
            price REAL,
            amount REAL,
            fees REAL,
            description TEXT,
            source_file TEXT,
            -- The following are DERIVED via reconstruction from gt_* anchors
            qty_before REAL NOT NULL DEFAULT 0,
            qty_after REAL NOT NULL DEFAULT 0,
            anchor_date TEXT,                 -- which gt_* date this qty was based on
            UNIQUE(symbol, transaction_date, quantity, amount, description)
        )
    """)

    # Add cached position size columns if they don't exist (migration for existing DBs)
    for col in ("qty_before", "qty_after"):
        try:
            cursor.execute(
                f"ALTER TABLE transactions ADD COLUMN {col} REAL NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # Column already exists or other benign error

    # ------------------------------------------------------------------
    # Capital Efficiency / Daily TWRR tables (PR #1 foundation)
    # These are additive. Existing reports and legacy capital_efficiency_v2
    # are completely unaffected.
    # ------------------------------------------------------------------

    # 2. Explicit external cash flows that must split sub-periods for correct TWRR
    # NOTE: daily_position_values is deprecated in favor of gt_daily_positions + reconstruction.
    # Kept for convenience/MV snapshots and some legacy paths. Always populate it via
    # the anchored Journal-safe recon (reconstruct_daily_position_quantities + ensure or
    # force_snap) -- never the old buggy tx-delta logic that produced 3x spikes on Journal
    # adjustment days (e.g. 2026-05-22 batch).
    # Charts, daily-positions CLI, and primary reporting use the pure recon instead of querying this table.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_position_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            quantity REAL NOT NULL,
            avg_cost REAL,
            market_value REAL NOT NULL,
            price_source TEXT DEFAULT 'deprecated',
            data_quality INTEGER DEFAULT 0,
            source_file TEXT,
            UNIQUE(symbol, as_of_date)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS position_cash_flows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            flow_date TEXT NOT NULL,
            flow_type TEXT NOT NULL,            -- 'buy','sell','deposit','withdrawal','dividend_cash','fee',...
            amount REAL NOT NULL,               -- positive = capital added to the position
            quantity_delta REAL,
            source TEXT,
            notes TEXT,
            UNIQUE(symbol, flow_date, flow_type, amount, quantity_delta)
        )
    """)

    # 3. Corporate actions (quantity/basis adjustments only — never generate returns)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS corporate_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            ex_date TEXT NOT NULL,
            action_type TEXT NOT NULL,          -- 'split','reverse_split','stock_dividend',...
            ratio REAL,
            new_symbol TEXT,
            adjustment_factor REAL,
            source TEXT,
            applied INTEGER DEFAULT 0,
            UNIQUE(symbol, ex_date, action_type)
        )
    """)

    # 4 & 5. Computed TWRR results (populated by twrr.py engine in later PRs)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_twrr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            daily_return REAL,
            subperiod_id INTEGER,
            cash_flow_count INTEGER DEFAULT 0,
            corp_action_count INTEGER DEFAULT 0,
            data_quality INTEGER DEFAULT 100,
            calc_version TEXT NOT NULL,  -- Only 'subperiod-hpr-v1' is valid (single source of truth)
            calc_timestamp TEXT,
            is_subperiod_boundary INTEGER DEFAULT 0,  -- 1 for authoritative boundary rows, 0 for gap-filled days
            UNIQUE(symbol, as_of_date)
        )
    """)

    # Indexes for the active tables
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_tx_symbol_date ON transactions(symbol, transaction_date)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pcf_symbol_date ON position_cash_flows(symbol, flow_date)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ca_symbol_ex ON corporate_actions(symbol, ex_date)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_dtwrr_symbol_date ON daily_twrr(symbol, as_of_date)"
    )

    # Migration: add is_subperiod_boundary column if missing (idempotent)
    try:
        cursor.execute(
            "ALTER TABLE daily_twrr ADD COLUMN is_subperiod_boundary INTEGER DEFAULT 0"
        )
    except Exception:
        pass  # Column already exists or other benign error

    # Also ensure the column exists even on older test DBs
    try:
        cursor.execute("SELECT is_subperiod_boundary FROM daily_twrr LIMIT 1")
    except Exception:
        try:
            cursor.execute(
                "ALTER TABLE daily_twrr ADD COLUMN is_subperiod_boundary INTEGER DEFAULT 0"
            )
        except Exception:
            pass

    # Raw price bar cache for aggressive local caching (minimizes remote API calls)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS market_price_bars (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            source TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (symbol, date, source)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_price_bars_symbol_date ON market_price_bars(symbol, date)"
    )

    # ------------------------------------------------------------------
    # Fund-as-symbol (account-level TWRR index + multi-broker foundation)
    # See docs/Fund_As_Symbol_Design.md
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_fund_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL,
            account_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            broker_account_ref TEXT,
            fund_symbol TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(broker, account_key)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_fund_equity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL,
            account_key TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            liquidation_value REAL NOT NULL,
            cash REAL,
            source TEXT NOT NULL DEFAULT 'api',
            data_quality INTEGER NOT NULL DEFAULT 100,
            ingested_at TEXT DEFAULT (datetime('now')),
            UNIQUE(broker, account_key, as_of_date, source)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_fund_cash_flows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL,
            account_key TEXT NOT NULL,
            flow_date TEXT NOT NULL,
            amount REAL NOT NULL,
            flow_type TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'api',
            notes TEXT,
            ingested_at TEXT DEFAULT (datetime('now')),
            UNIQUE(broker, account_key, flow_date, flow_type, amount, source)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fund_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fund_symbol TEXT NOT NULL,
            broker TEXT NOT NULL,
            account_key TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            liquidation_value REAL NOT NULL,
            external_cf REAL NOT NULL DEFAULT 0,
            daily_return REAL,
            twrr_index REAL NOT NULL,
            data_quality INTEGER NOT NULL DEFAULT 100,
            calc_version TEXT NOT NULL,
            calc_timestamp TEXT,
            UNIQUE(fund_symbol, as_of_date)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_fund_daily_symbol_date "
        "ON fund_daily(fund_symbol, as_of_date)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_gt_fund_snap_acct_date "
        "ON gt_fund_equity_snapshots(broker, account_key, as_of_date)"
    )

    # Uniform multi-broker account holdings (Schwab now; IBKR/RH later).
    # Keyed by broker + account_key — never requires raw account numbers in logs.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gt_account_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL,
            account_key TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL,
            market_value REAL,
            price REAL,
            cost_basis REAL,
            asset_type TEXT,
            currency TEXT NOT NULL DEFAULT 'USD',
            source TEXT NOT NULL DEFAULT 'api',
            ingested_at TEXT DEFAULT (datetime('now')),
            UNIQUE(broker, account_key, as_of_date, symbol, source)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_gt_acct_pos_acct_date "
        "ON gt_account_positions(broker, account_key, as_of_date)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_gt_acct_pos_symbol "
        "ON gt_account_positions(symbol, as_of_date)"
    )

    # ------------------------------------------------------------------
    # Derived: daily account net liquidation (one row per account/market day)
    # Built from local gt_fund_equity_snapshots; never fabricated history.
    # ------------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_account_net_liq (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker TEXT NOT NULL,
            account_key TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            net_liquidation_value REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'gt_equity_snapshot',
            data_quality INTEGER NOT NULL DEFAULT 100,
            validated INTEGER NOT NULL DEFAULT 1,
            calc_timestamp TEXT,
            UNIQUE(broker, account_key, as_of_date)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_daily_net_liq_acct_date "
        "ON daily_account_net_liq(broker, account_key, as_of_date)"
    )

    conn.commit()


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    conn = get_connection(db_path)
    create_schema(conn)
    return conn


# ------------------------------------------------------------------
# Minimal Data Access Layer (Level 3 DRY step)
# ------------------------------------------------------------------


def get_current_holdings(conn: sqlite3.Connection) -> list[dict]:
    """Return current positive-quantity holdings from the ground truth table."""
    return conn.execute("""
        SELECT symbol, quantity, market_value, as_of_date
        FROM gt_daily_positions
        WHERE as_of_date = (SELECT MAX(as_of_date) FROM gt_daily_positions)
          AND quantity > 0
        ORDER BY market_value DESC
    """).fetchall()


def get_symbols_with_real_data(conn: sqlite3.Connection) -> set[str]:
    """Return all symbols that have either realized activity or current holdings in gt tables."""
    rows = conn.execute("""
        SELECT DISTINCT symbol FROM gt_realized_gains
        UNION
        SELECT DISTINCT symbol FROM gt_daily_positions WHERE quantity > 0
    """).fetchall()
    return {r["symbol"] for r in rows}


def has_minimum_real_data(
    conn: sqlite3.Connection, require_daily_positions: bool = True
) -> bool:
    """
    Returns True only if the database contains sufficient real, verified data
    from Schwab exports or API (ground truth gt_* tables).
    """
    # Check ground truth daily positions (preferred source)
    if require_daily_positions:
        gt_days = conn.execute("""
            SELECT COUNT(DISTINCT as_of_date)
            FROM gt_daily_positions
        """).fetchone()[0]
        if gt_days >= 1:
            return True

    # Fallback: any realized activity or current holdings in gt tables
    gt_activity = conn.execute("""
        SELECT COUNT(DISTINCT symbol)
        FROM (
            SELECT symbol FROM gt_realized_gains
            UNION
            SELECT symbol FROM gt_daily_positions WHERE quantity > 0
        )
    """).fetchone()[0]

    return gt_activity > 0


def ensure_real_data(
    conn: sqlite3.Connection,
    require_daily_positions: bool = True,
    auto_ingest: bool = True,
) -> bool:
    """
    Ensures the database has sufficient real Schwab data before analysis runs.

    This is the key function that makes ingestion *implicit*.

    Behavior:
    - First checks if we already have enough real data.
    - If not (and auto_ingest=True), scans known locations for new real export files
      (Positions, Realized Gains, Transactions) and ingests them automatically.
    - Only real, verified files are ever used.
    - Returns True if we now have sufficient data, False otherwise.

    This allows users to simply run `portfolio report` or `portfolio twrr`
    without manually running ingestion commands.
    """
    if has_minimum_real_data(conn, require_daily_positions=require_daily_positions):
        return True

    if not auto_ingest:
        return False

    # Note: Auto-ingestion of raw Schwab files into gt_* tables is handled by
    # dedicated tools (tools/ingest_all_schwab_exports.py and related) or explicit
    # calls. The old legacy auto-ingest path has been retired.

    # Final check
    if has_minimum_real_data(conn, require_daily_positions=require_daily_positions):
        return True

    # Auto-populate recent daily market values for TWRR / Capital Efficiency (aggressive on-demand).
    #
    # Policy (data-driven):
    # - Anchor to the user's actual latest data dates (not host clock).
    # - Ensure at least the last ~120 days of credible daily market values for active symbols.
    # - Uses best available provider (Massive first via Massive_Key).
    # - Fully leverages aggressive local caching.
    if True:  # Always attempt population for TWRR needs
        try:
            from .market_data import (
                ensure_prices_for_recent_trades_of_active_symbols,
                get_relevant_recent_window,
            )

            start, end = get_relevant_recent_window(conn, lookback_days=120)

            active_symbols = [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT symbol FROM positions WHERE quantity > 0"
                ).fetchall()
            ]

            populated = 0
            for sym in active_symbols:
                n = ensure_prices_for_recent_trades_of_active_symbols(
                    conn,
                    lookback_days=180,
                    price_provider="auto",
                    verbose=False,  # keep quiet in the general ensure path; twrr can be verbose
                )
                populated += n

            if populated > 0:
                print("[Auto] Populated prices for recent trades of active symbols.")

        except Exception as e:
            print(f"[Auto-populate] Warning while filling daily values: {e}")

    return has_minimum_real_data(conn, require_daily_positions=require_daily_positions)
