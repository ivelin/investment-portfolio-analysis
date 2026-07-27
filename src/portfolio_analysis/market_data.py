"""
Market data helpers for fetching credible historical prices and computing
daily position market values.

This module supports the "credible source of truth" rule:
- Direct Schwab data is preferred when available.
- Reputable external providers (yfinance, Polygon, etc.) are used for
  historical closing prices when direct daily snapshots are missing.
- All sources are explicitly tagged.
"""

from datetime import datetime, timedelta
from typing import Optional, List
import sqlite3

import os

import pandas as pd
import requests
import warnings
import logging

from .db import get_connection


_yf = None


def _get_yf():
    """Lazily load yfinance only when the fallback provider is actually selected.

    This preserves the existing multi-provider chain (Massive → FMP → Twelve →
    Alpha Vantage → yfinance last) while avoiding a hard runtime dependency.
    All quieting of yfinance spam is applied on first use.
    """
    global _yf
    if _yf is None:
        import yfinance as yf

        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        warnings.filterwarnings("ignore", category=FutureWarning)
        warnings.filterwarnings("ignore", message=".*possibly delisted.*")
        warnings.filterwarnings("ignore", message=".*1 Failed download.*")
        _yf = yf
    return _yf


def _get_polygon_key() -> Optional[str]:
    """Load Polygon/Massive key from environment (supports Massive_Key as alias).

    Also attempts to load from common .env locations if the key is not already
    in os.environ (many CLI runs under uv do not inherit the shell's exported vars).
    """
    key = os.environ.get("POLYGON_API_KEY") or os.environ.get("Massive_Key")
    if key:
        return key

    # Prefer instance-home .env; legacy home/hermes paths as fallbacks.
    from .paths import env_file_candidates

    candidates = [str(p) for p in env_file_candidates()]
    for path in candidates:
        try:
            if os.path.isfile(path):
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("Massive_Key="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                os.environ["Massive_Key"] = val
                                return val
                        if line.startswith("POLYGON_API_KEY="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                os.environ["POLYGON_API_KEY"] = val
                                return val
        except Exception:
            pass
    return None


def _get_fmp_key() -> Optional[str]:
    """Financial Modeling Prep key."""
    key = os.environ.get("FMP_API_KEY") or os.environ.get("FMP_API_Key")
    if key:
        return key
    from .paths import env_file_candidates

    for path in env_file_candidates():
        try:
            if path.is_file():
                with open(path) as f:
                    for line in f:
                        if line.strip().startswith(("FMP_API_KEY=", "FMP_API_Key=")):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                os.environ["FMP_API_Key"] = val
                                return val
        except Exception:
            pass
    return None


def _get_twelve_key() -> Optional[str]:
    """Twelve Data key."""
    key = os.environ.get("TWELVE_DATA_API_KEY") or os.environ.get("TwelveData_API_Key")
    if key:
        return key
    from .paths import env_file_candidates

    for path in env_file_candidates():
        try:
            if path.is_file():
                with open(path) as f:
                    for line in f:
                        if "TwelveData" in line or "TWELVE_DATA" in line:
                            if "=" in line:
                                val = (
                                    line.split("=", 1)[1].strip().strip('"').strip("'")
                                )
                                if val:
                                    os.environ["TwelveData_API_Key"] = val
                                    return val
        except Exception:
            pass
    return None


def _get_alphavantage_key() -> Optional[str]:
    """Alpha Vantage key."""
    key = os.environ.get("ALPHAVANTAGE_API_KEY") or os.environ.get(
        "Alpha_Vantage_API_Key"
    )
    if key:
        return key
    from .paths import env_file_candidates

    for path in env_file_candidates():
        try:
            if path.is_file():
                with open(path) as f:
                    for line in f:
                        if "Alpha_Vantage" in line or "ALPHAVANTAGE" in line:
                            if "=" in line:
                                val = (
                                    line.split("=", 1)[1].strip().strip('"').strip("'")
                                )
                                if val:
                                    os.environ["Alpha_Vantage_API_Key"] = val
                                    return val
        except Exception:
            pass
    return None


def _get_latest_known_real_date(
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[str]:
    """Return the most recent date for which the user has provided real data
    (latest daily_position_values or latest transaction). Used to avoid
    pointless network calls for future/simulated dates.
    """
    if conn is None:
        conn = get_connection()
    row = conn.execute("""
        SELECT MAX(d) as d FROM (
            SELECT MAX(as_of_date) as d FROM daily_position_values
            UNION
            SELECT MAX(transaction_date) as d FROM gt_transactions
        )
    """).fetchone()
    return row["d"] if row and row["d"] else None


def _date_is_after_known_data(d: str, latest: Optional[str]) -> bool:
    """True if d is clearly after the last real data point the user has."""
    if not latest:
        return False
    try:
        return d > latest
    except Exception:
        return False


# ------------------------------------------------------------------
# Local Price Bar Cache (aggressive caching to minimize remote calls)
# ------------------------------------------------------------------


def _load_from_cache(
    symbols: List[str], start_date: str, end_date: str, source: Optional[str] = None
) -> pd.DataFrame:
    """Load cached bars from the local DB for the given symbols and date range."""
    conn = get_connection()

    # Ensure the cache table exists (defensive)
    conn.execute("""
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

    placeholders = ",".join(["?"] * len(symbols))
    query = f"""
        SELECT symbol, date, close, source
        FROM market_price_bars
        WHERE symbol IN ({placeholders})
          AND date BETWEEN ? AND ?
    """
    params = symbols + [start_date, end_date]
    if source:
        query += " AND source = ?"
        params.append(source)

    try:
        df = pd.read_sql(query, conn, params=params)
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Dedup in case multiple sources have the same (symbol, date) — common
    # after hybrid provider usage. Keep last (most recent in result order).
    df = df.drop_duplicates(subset=["date", "symbol"], keep="last")
    df["date"] = pd.to_datetime(df["date"])
    pivot = df.pivot(index="date", columns="symbol", values="close")
    return pivot


def _save_to_cache(prices_df: pd.DataFrame, source: str):
    """Save fetched price bars to the local cache table."""
    if prices_df.empty:
        return

    conn = get_connection()
    now = datetime.now().isoformat()

    rows = []
    for date, row in prices_df.iterrows():
        date_str = date.strftime("%Y-%m-%d")
        for symbol, close in row.items():
            if pd.notna(close):
                rows.append((symbol, date_str, float(close), source, now))

    if rows:
        conn.executemany(
            """
            INSERT OR REPLACE INTO market_price_bars
            (symbol, date, close, source, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def fetch_historical_prices(
    symbols: List[str],
    start_date: str,
    end_date: str,
    provider: str = "auto",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Fetch historical daily close prices with aggressive local caching.

    Strategy:
    - Check the local `market_price_bars` cache first for the requested range + source.
    - Only call the remote provider for dates we don't have cached for that source.
    - Write newly fetched bars back to the cache.
    - This ensures repetitive calls (twrr, reports, etc.) do not cause repeated remote API hits.
    """
    provider = provider.lower()

    # Build fallback chain
    if provider == "auto":
        chain = get_provider_chain()
    else:
        chain = [provider]

    # Short-circuit obviously future dates before any network work
    latest_known = _get_latest_known_real_date()
    if _date_is_after_known_data(
        start_date, latest_known
    ) and _date_is_after_known_data(end_date, latest_known):
        return pd.DataFrame()

    # Ultra-aggressive cross-source cache check:
    # If we have EVER successfully stored a close for these symbols in this date range
    # from *any* provider, return the best available cached data without touching any API.
    # This is the main defense against rate limits on Massive / FMP / TwelveData etc.
    if use_cache:
        any_cache = _load_from_cache(
            symbols, start_date, end_date, source=None
        )  # no source filter
        if not any_cache.empty and all(sym in any_cache.columns for sym in symbols):
            return any_cache.dropna(how="all")

    combined = pd.DataFrame()

    for prov in chain:
        prov = prov.lower()
        if prov in ("massive", "polygon"):
            prov = "massive"

        # 1. Load whatever we already have for this provider (aggressive caching!)
        cached = pd.DataFrame()
        if use_cache:
            cached = _load_from_cache(symbols, start_date, end_date, source=prov)

        # 2. Aggressive cache check: if we already have data for the requested symbols
        #    in this date range from this provider, DO NOT hit the remote API.
        #    This is the entire reason for the caching layer — to survive rate limits.
        if not cached.empty and all(sym in cached.columns for sym in symbols):
            # We have previously cached data for these symbols in the requested window.
            # Return it immediately. No remote call.
            return cached.dropna(how="all")

        # 3. Cache is incomplete — only now do we hit the remote for this provider
        fetched = pd.DataFrame()

        if prov == "massive":
            key = _get_polygon_key()
            if key:
                try:
                    fetched = _fetch_via_massive(symbols, start_date, end_date, key)
                except Exception:
                    fetched = pd.DataFrame()

        elif prov == "fmp":
            key = _get_fmp_key()
            if key:
                try:
                    fetched = _fetch_via_fmp(symbols, start_date, end_date, key)
                except Exception:
                    fetched = pd.DataFrame()

        elif prov in ("twelvedata", "twelve"):
            key = _get_twelve_key()
            if key:
                try:
                    fetched = _fetch_via_twelve(symbols, start_date, end_date, key)
                except Exception:
                    fetched = pd.DataFrame()

        elif prov in ("alphavantage", "alpha"):
            key = _get_alphavantage_key()
            if key:
                try:
                    fetched = _fetch_via_alphavantage(
                        symbols, start_date, end_date, key
                    )
                except Exception:
                    fetched = pd.DataFrame()

        elif prov == "yfinance":
            yf = _get_yf()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    data = yf.download(
                        symbols,
                        start=start_date,
                        end=end_date,
                        progress=False,
                        auto_adjust=True,
                        threads=True,
                    )
                except Exception:
                    data = pd.DataFrame()

            if not data.empty:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if "Close" in data.columns.get_level_values(0):
                            fetched = data["Close"].copy()
                        else:
                            fetched = data.iloc[
                                :, data.columns.get_level_values(0) == "Close"
                            ].copy()
                            if (
                                isinstance(fetched, pd.DataFrame)
                                and len(fetched.columns) > 0
                            ):
                                fetched = fetched.droplevel(0, axis=1)
                    else:
                        if "Close" in data.columns:
                            fetched = data[["Close"]].copy()
                            fetched.columns = (
                                symbols if len(symbols) > 1 else [symbols[0]]
                            )
                        else:
                            fetched = data.copy()
                    fetched = fetched.dropna(how="all")
                except Exception:
                    fetched = pd.DataFrame()

        # 4. Merge whatever we just fetched with the existing cache for this source
        if not fetched.empty:
            if not cached.empty:
                combined = fetched.combine_first(cached)
            else:
                combined = fetched

            if use_cache:
                _save_to_cache(fetched, prov)
            return combined.dropna(how="all")

        # Provider gave us nothing new; fall back to whatever was cached (if anything)
        if not cached.empty:
            combined = cached

    # Nothing from any provider in the chain
    return combined.dropna(how="all") if not combined.empty else pd.DataFrame()


def _fetch_via_massive(
    symbols: List[str], start_date: str, end_date: str, api_key: str
) -> pd.DataFrame:
    """
    Fetch daily aggregates using Massive's REST API (the provider behind the Massive_Key).
    Follows their documented aggregates endpoint.
    """
    base_url = "https://api.massive.com"
    results = {}

    for symbol in symbols:
        url = (
            f"{base_url}/v2/aggs/ticker/{symbol}/range/1/day/"
            f"{start_date}/{end_date}"
            f"?adjusted=true&sort=asc&limit=50000&apiKey={api_key}"
        )
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "OK" or not data.get("results"):
            # Non-fatal for individual symbols (e.g. rate limits, no data)
            continue

        df = pd.DataFrame(data["results"])
        df["date"] = pd.to_datetime(df["t"], unit="ms").dt.date
        df = df.set_index("date")["c"]  # close price
        results[symbol] = df

    if not results:
        return pd.DataFrame()

    prices = pd.DataFrame(results)
    prices.index = pd.to_datetime(prices.index)
    return prices.dropna(how="all")


def _fetch_via_fmp(
    symbols: List[str], start_date: str, end_date: str, api_key: str
) -> pd.DataFrame:
    """Financial Modeling Prep daily closes."""
    results = {}
    for symbol in symbols:
        url = (
            "https://financialmodelingprep.com/api/v3/historical-price-full/"
            f"{symbol}?from={start_date}&to={end_date}&apikey={api_key}"
        )
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            hist = data.get("historical") or []
            if not hist:
                continue
            df = pd.DataFrame(hist)
            if "date" not in df.columns or "close" not in df.columns:
                continue
            df = df[["date", "close"]].copy()
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df.set_index("date")["close"]
            results[symbol] = df
        except Exception:
            continue  # try next symbol or fall through to next provider

    if not results:
        return pd.DataFrame()
    prices = pd.DataFrame(results)
    prices.index = pd.to_datetime(prices.index)
    return prices.dropna(how="all")


def _fetch_via_twelve(
    symbols: List[str], start_date: str, end_date: str, api_key: str
) -> pd.DataFrame:
    """Twelve Data time series (1day)."""
    results = {}
    for symbol in symbols:
        url = (
            "https://api.twelvedata.com/time_series"
            f"?symbol={symbol}&interval=1day&start_date={start_date}"
            f"&end_date={end_date}&apikey={api_key}"
        )
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            vals = data.get("values") or []
            if not vals:
                continue
            df = pd.DataFrame(vals)
            if "datetime" not in df.columns or "close" not in df.columns:
                continue
            df = df[["datetime", "close"]].copy()
            df["date"] = pd.to_datetime(df["datetime"]).dt.date
            df = df.set_index("date")["close"].astype(float)
            results[symbol] = df
        except Exception:
            continue

    if not results:
        return pd.DataFrame()
    prices = pd.DataFrame(results)
    prices.index = pd.to_datetime(prices.index)
    return prices.dropna(how="all")


def _fetch_via_alphavantage(
    symbols: List[str], start_date: str, end_date: str, api_key: str
) -> pd.DataFrame:
    """Alpha Vantage TIME_SERIES_DAILY."""
    results = {}
    for symbol in symbols:
        url = (
            "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
            f"&symbol={symbol}&apikey={api_key}&outputsize=full"
        )
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            ts = data.get("Time Series (Daily)") or {}
            if not ts:
                continue
            rows = []
            for d, v in ts.items():
                close = v.get("4. close")
                if close:
                    rows.append((d, float(close)))
            if not rows:
                continue
            df = pd.DataFrame(rows, columns=["date", "close"])
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df = df.set_index("date")["close"]
            # filter to requested range
            df = df[
                (df.index >= pd.to_datetime(start_date).date())
                & (df.index <= pd.to_datetime(end_date).date())
            ]
            results[symbol] = df
        except Exception:
            continue

    if not results:
        return pd.DataFrame()
    prices = pd.DataFrame(results)
    prices.index = pd.to_datetime(prices.index)
    return prices.dropna(how="all")


def get_provider_chain() -> list[str]:
    """Return ordered list of providers to try, based on which keys are present."""
    chain = []
    if _get_polygon_key():
        chain.append("massive")
    if _get_fmp_key():
        chain.append("fmp")
    if _get_twelve_key():
        chain.append("twelvedata")
    if _get_alphavantage_key():
        chain.append("alphavantage")
    chain.append("yfinance")
    return chain


def get_position_quantity_on_date(
    conn: sqlite3.Connection, symbol: str, as_of_date: str
) -> float:
    """
    Reconstruct the quantity held of a symbol on a specific date.

    Anchors to latest gt_daily_positions snapshot <= as_of_date, then applies
    only subsequent tx deltas (skipping Journal tx which are internal adjustments).
    This fixes starting from zero and bad data in derived tables.

    NOTE (DRY/MECE): For a *full daily series* (e.g. charting step function)
    prefer reconstruct_daily_position_quantities (daily_positions.py). This
    point getter is used internally by ensure_daily_market_values for
    incremental population of the (deprecated) daily_position_values cache.
    Charts and reporting delegate to the series recon via reporting.get_daily_position_series_for_symbol.
    """
    # Anchor to latest gt_daily_positions (per requirements; high trust Positions export)
    anchor = conn.execute(
        """
        SELECT as_of_date, quantity FROM gt_daily_positions
        WHERE symbol = ? AND as_of_date <= ?
        ORDER BY as_of_date DESC LIMIT 1
        """,
        (symbol, as_of_date),
    ).fetchone()

    if anchor:
        anchor_date = anchor[0]
        qty = float(anchor[1] or 0)
    else:
        anchor_date = "1900-01-01"
        qty = 0.0

    # Apply tx strictly after anchor
    tx_rows = conn.execute(
        """
        SELECT quantity, transaction_type FROM gt_transactions
        WHERE symbol = ? AND transaction_date > ? AND transaction_date <= ?
        ORDER BY transaction_date, id
        """,
        (symbol, anchor_date, as_of_date),
    ).fetchall()

    for tx in tx_rows:
        raw = float(tx[0] or 0)
        ttype = (tx[1] or "").lower()
        if "journal" in ttype:
            continue  # internal adjustment/transfer, do not affect position size
        delta = abs(raw)
        is_reducing = any(
            kw in ttype for kw in ["sell", "sold", "sell to open", "sell short"]
        )
        if is_reducing:
            qty = max(qty - delta, 0.0)
        else:
            qty += delta

    return max(qty, 0.0)


def get_relevant_recent_window(
    conn: sqlite3.Connection, lookback_days: int = 120
) -> tuple[str, str]:
    """
    Return a (start_date, end_date) window based on the user's actual data,
    not the host clock. This makes population "as long back as needed"
    for the user's real holdings.
    """
    # Find the latest date across the user's relevant tables
    max_dates = []

    for table, col in [
        ("positions", "as_of_date"),
        ("realized_gains", "closed_date"),
        ("transactions", "transaction_date"),
    ]:
        row = conn.execute(f"SELECT MAX({col}) as d FROM {table}").fetchone()
        if row and row["d"]:
            max_dates.append(row["d"])

    if not max_dates:
        # Fallback to last 120 days from now
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        return start, end

    try:
        latest = max(pd.to_datetime(d) for d in max_dates if d)
    except Exception:
        latest = pd.Timestamp.now()

    end = latest.strftime("%Y-%m-%d")
    start = (latest - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    return start, end


def ensure_prices_for_recent_trades_of_active_symbols(
    conn: sqlite3.Connection,
    lookback_days: int = 180,
    price_provider: str = "auto",
    verbose: bool = True,
    symbols: Optional[List[str]] = None,
) -> int:
    """
    Aggressive on-demand population for the **pure transaction-log** TWRR model.

    For every currently active symbol we guarantee credible daily close prices on:
    - All real trade dates inside the lookback window (from the transactions table)
    - The five critical window-boundary dates (today-30, today-60, today-90, YTD start, today)

    This ensures that even symbols with **zero trades** inside a 90-day window still have
    the two boundary prices needed to produce a valid single-sub-period TWRR (pure price return
    on the quantity reconstructed from the full transaction history).

    Never requires or reads historical position snapshots for the TWRR calculation.
    """
    from datetime import datetime, timedelta

    today = datetime.now()
    end = today.strftime("%Y-%m-%d")
    start = (today - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    # Fixed valuation boundaries we always need for the rolling windows
    boundary_dates = {
        (today - timedelta(days=30)).strftime("%Y-%m-%d"),
        (today - timedelta(days=60)).strftime("%Y-%m-%d"),
        (today - timedelta(days=90)).strftime("%Y-%m-%d"),
        f"{today.year}-01-01",
        end,
    }

    if symbols:
        active_symbols = [s.upper() for s in symbols]
    else:
        active_symbols = [
            r[0]
            for r in conn.execute(
                """
                SELECT DISTINCT symbol
                FROM gt_daily_positions
                WHERE as_of_date = (SELECT MAX(as_of_date) FROM gt_daily_positions)
                  AND quantity > 0
                ORDER BY symbol
                """
            ).fetchall()
        ]

    total_new_prices = 0
    latest_known = _get_latest_known_real_date(conn)

    for symbol in active_symbols:
        # 1. Real trade dates in the window
        trade_rows = conn.execute(
            """
            SELECT DISTINCT transaction_date
            FROM gt_transactions
            WHERE symbol = ?
              AND transaction_date BETWEEN ? AND ?
            ORDER BY transaction_date
            """,
            (symbol, start, end),
        ).fetchall()
        dates = {row["transaction_date"] for row in trade_rows}

        # 2. Always add the window boundaries (even if no trade on that exact day)
        dates.update(boundary_dates)

        # 3. Never attempt network fetches for dates after the user's last real data
        #    (this eliminates all the "AAPL possibly delisted" spam in a 2026 sim).
        if latest_known:
            dates = {d for d in dates if d <= latest_known}

        # Sort for nicer logging
        date_list = sorted(dates)

        if date_list:
            # Aggressive cache pre-check: if we already have *all* the needed dates
            # for this symbol in the DB (from any previous provider), skip entirely.
            # This is what prevents pointless re-fetching and rate-limit pain.
            placeholders = ",".join(["?"] * len(date_list))
            existing = conn.execute(
                f"""
                SELECT COUNT(DISTINCT date)
                FROM market_price_bars
                WHERE symbol = ? AND date IN ({placeholders})
                """,
                [symbol] + date_list,
            ).fetchone()[0]

            if existing >= len(date_list):
                # Fully cached from previous runs — zero work, no fetch, no spam
                continue

            # Some dates are missing — fetch the full range (the inner function
            # will still use its own cache for what it can, and only hit APIs for gaps).
            min_d = min(date_list)
            max_d = max(date_list)
            df = fetch_historical_prices(
                [symbol], min_d, max_d, provider=price_provider, use_cache=True
            )
            if not df.empty:
                got = set(df.index.strftime("%Y-%m-%d")) if not df.empty else set()
                newly_covered = len([d for d in date_list if d in got])
                total_new_prices += newly_covered

            if verbose:
                print(
                    f"[Auto] Ensured prices for {len(date_list)} dates ({len(trade_rows)} trades + boundaries) of {symbol}"
                )

    if verbose and total_new_prices > 0:
        print(
            f"[Auto] Price population complete for active symbols (last {lookback_days} days + boundaries)."
        )

    return total_new_prices


def ensure_daily_market_values(
    conn: sqlite3.Connection,
    symbol: str,
    start_date: str,
    end_date: str,
    price_provider: str = "auto",
) -> int:
    """
    For a symbol and date range, ensure we have a row in daily_position_values
    for every trading day.

    - If a high-quality Schwab row already exists for that date, keep it.
    - Otherwise, calculate quantity from the user's data and fetch price
      from the chosen provider, then insert with appropriate price_source.

    Returns the number of new rows created.
    """
    prices = fetch_historical_prices([symbol], start_date, end_date, price_provider)

    if prices.empty:
        return 0

    created = 0

    for date, row in prices.iterrows():
        date_str = date.strftime("%Y-%m-%d")
        close_price = row[symbol]

        if pd.isna(close_price):
            continue

        # Check if we already have good data for this date
        existing = conn.execute(
            """
            SELECT price_source, data_quality
            FROM daily_position_values
            WHERE symbol = ? AND as_of_date = ?
            """,
            (symbol, date_str),
        ).fetchone()

        if existing and existing["price_source"] in ("schwab_export", "schwab_api"):
            # We have real Schwab data — do not overwrite
            continue

        # Calculate quantity held on this date from user's real data
        qty = get_position_quantity_on_date(conn, symbol, date_str)

        if qty <= 0:
            continue

        market_value = round(qty * float(close_price), 2)

        # Insert or update with the external price source
        conn.execute(
            """
            INSERT OR REPLACE INTO daily_position_values
            (symbol, as_of_date, quantity, market_value, price_source, data_quality, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                symbol,
                date_str,
                qty,
                market_value,
                price_provider,
                75,
                f"{price_provider}_historical",
            ),
        )
        created += 1

    conn.commit()
    return created
