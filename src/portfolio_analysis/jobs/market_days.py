"""US equity market-day calendar (valid days for daily net-liq rows).

Weekends and major NYSE holidays are excluded. Observed Monday/Friday rules
cover fixed holidays that fall on weekends. Not a full exchange calendar —
good enough for gap-fill gating without external deps.
"""

from __future__ import annotations

from datetime import date, timedelta


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """nth weekday in month (weekday: Mon=0 … Sun=6). n=1 first, n=-1 last."""
    if n > 0:
        d = date(year, month, 1)
        while d.weekday() != weekday:
            d += timedelta(days=1)
        d += timedelta(weeks=n - 1)
        return d
    # last
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    while d.weekday() != weekday:
        d -= timedelta(days=1)
    return d


def _observed(d: date) -> date:
    """If holiday is Sat → Friday before; Sun → Monday after."""
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def us_equity_holidays(year: int) -> set[date]:
    """Major US equity market holidays for ``year`` (observed)."""
    fixed = [
        date(year, 1, 1),  # New Year's
        date(year, 6, 19),  # Juneteenth
        date(year, 7, 4),  # Independence Day
        date(year, 12, 25),  # Christmas
    ]
    floating = [
        _nth_weekday(year, 1, 0, 3),  # MLK Day
        _nth_weekday(year, 2, 0, 3),  # Presidents Day
        _nth_weekday(year, 5, 0, -1),  # Memorial Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
    ]
    out: set[date] = set()
    for d in fixed:
        out.add(_observed(d))
    out.update(floating)
    # Good Friday: Friday before Easter (Western)
    out.add(_good_friday(year))
    return out


def _good_friday(year: int) -> date:
    """Western Easter algorithm → Good Friday."""
    # Anonymous Gregorian algorithm
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    return easter - timedelta(days=2)


def is_us_market_day(d: date) -> bool:
    """True if ``d`` is a US equity regular session day (no weekend/holiday)."""
    if d.weekday() >= 5:
        return False
    return d not in us_equity_holidays(d.year)


def iter_market_days(start: date, end: date):
    """Yield each US market day in [start, end] inclusive."""
    if end < start:
        return
    cur = start
    while cur <= end:
        if is_us_market_day(cur):
            yield cur
        cur += timedelta(days=1)
