"""Single source of truth for the labor calendar of a vintage.

Before this module, the August 2026 cutoff was spelled out as a literal in
two dozen places (``pd.period_range('1993-01', '2026-08')`` and friends).
Every helper below defaults to the vintage frozen in the H36 delivery, so
migrating a call site to it is a pure refactor: the produced calendars are
identical, and ``tests/unit/test_cutoff.py`` proves that against the
original expressions.

Changing the vintage means changing ``FROZEN_CUTOFF`` in this one place or,
better, passing ``last`` explicitly from the vintage policy.
"""

from __future__ import annotations

import os

import pandas as pd

from icml.domain.periods import MonthlyPeriod

#: First month of every ICML labor series.
FIRST_MONTH: str = "1993-01"

#: Last month of the vintage frozen in the H36 delivery. It names that
#: vintage and never changes; the cutoff of a *run* is ``ACTIVE_CUTOFF``.
FROZEN_CUTOFF: str = "2026-08"

#: Environment variable that selects the cutoff of a run (``YYYY-MM``).
CUTOFF_ENV: str = "ICML_CUTOFF"


def _active_cutoff() -> str:
    """Return the cutoff of this process: the variable, else the frozen one.

    Calendars and panel shapes are fixed when the modules are imported, so
    the variable must be set **before** the interpreter starts (for example
    ``ICML_CUTOFF=2026-07 python -m icml ...``). A malformed value stops the
    import instead of producing a silently wrong calendar.
    """
    value = os.environ.get(CUTOFF_ENV, FROZEN_CUTOFF)
    MonthlyPeriod.parse(value)
    return value


#: Last month of the run in this process (``FROZEN_CUTOFF`` unless overridden).
ACTIVE_CUTOFF: str = _active_cutoff()

#: First month of the post-redesign informality signal (H5/H6/H9).
INFORMALITY_NEW_FIRST_MONTH: str = "2021-01"

#: First month of the official sectoral (branch) monthly series (H10/H16).
SECTORAL_FIRST_MONTH: str = "2015-01"


def _validated(value: str) -> str:
    """Return ``value`` if it is a ``YYYY-MM`` string, else raise."""
    MonthlyPeriod.parse(value)
    return str(value)


def _check_order(first: str, last: str) -> tuple[str, str]:
    first = _validated(first)
    last = _validated(last)
    if MonthlyPeriod.parse(last) < MonthlyPeriod.parse(first):
        raise ValueError(f"Cutoff {last} precedes first month {first}")
    return first, last


def month_periods(
    first: str = FIRST_MONTH, last: str = ACTIVE_CUTOFF
) -> pd.PeriodIndex:
    """Return the monthly ``PeriodIndex`` from ``first`` to ``last``."""
    first, last = _check_order(first, last)
    return pd.period_range(first, last, freq="M")


def month_labels(
    first: str = FIRST_MONTH, last: str = ACTIVE_CUTOFF
) -> list[str]:
    """Return the ``YYYY-MM`` labels from ``first`` to ``last``."""
    return month_periods(first, last).astype(str).tolist()


def month_starts(
    first: str = FIRST_MONTH, last: str = ACTIVE_CUTOFF
) -> pd.DatetimeIndex:
    """Return month-start timestamps (``freq='MS'``) from ``first``."""
    first, last = _check_order(first, last)
    return pd.date_range(f"{first}-01", f"{last}-01", freq="MS")


def expected_month_count(
    first: str = FIRST_MONTH, last: str = ACTIVE_CUTOFF
) -> int:
    """Return how many months a complete series must contain."""
    return len(month_periods(first, last))


def shift_label(period: str, months: int) -> str:
    """Return the ``YYYY-MM`` label ``months`` months after ``period``."""
    return str(MonthlyPeriod.parse(period).shift(months))


def next_month(period: str = ACTIVE_CUTOFF) -> str:
    """Return the month that follows ``period`` (default: the cutoff)."""
    return shift_label(period, 1)


def trailing_window_label(period: str, length: int = 3) -> str:
    """Return ``"first/last"`` for the ``length`` months ending at ``period``.

    DANE publishes informal employment and social security as three-month
    moving windows, so the annex matching GEIH month ``2026-09`` covers
    ``2026-07/2026-09``.
    """
    if length < 1:
        raise ValueError(f"Window length must be positive, got {length}")
    return f"{shift_label(period, 1 - length)}/{period}"


#: Months of the run (404 for the frozen vintage, 1993-01 .. 2026-08).
N_MONTHS: int = expected_month_count()

#: Rows of a complete panel of 33 territories (departments or urban
#: domains) over every month of the run.
ROWS_33: int = 33 * N_MONTHS

#: Rows of the two national series (DANE reference and ICML complete).
ROWS_NATIONAL: int = 2 * N_MONTHS


#: Year and month of the run's last month (2026 and 8 for the frozen vintage).
LAST_YEAR: int = int(ACTIVE_CUTOFF[:4])
LAST_MONTH: int = int(ACTIVE_CUTOFF[5:])

#: Months of the post-redesign informality signal (68 for the frozen vintage).
RECENT_MONTHS: int = expected_month_count(INFORMALITY_NEW_FIRST_MONTH)

#: Months of the official sectoral series (140 for the frozen vintage).
SECTORAL_MONTHS: int = expected_month_count(SECTORAL_FIRST_MONTH)

#: Rolling three-month windows of the 13-city informality annex, which start
#: with the window ending in 2021-03 (66 for the frozen vintage).
CITY13_WINDOWS: int = expected_month_count("2021-03")


def vintage_suffix(cutoff: str = ACTIVE_CUTOFF) -> str:
    """Return ``YYYY_MM`` for file names that identify a vintage."""
    return _validated(cutoff).replace("-", "_")
