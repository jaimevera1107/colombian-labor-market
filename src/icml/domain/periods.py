"""Monthly period handling.

Periods are represented as ``YYYY-MM`` strings in every ICML table, which
keeps CSV outputs stable and human-readable.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pandas as pd

_PERIOD_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])$")


@dataclass(frozen=True, order=True)
class MonthlyPeriod:
    """A calendar month.

    Attributes
    ----------
    year : int
        Calendar year.
    month : int
        Month number in ``1..12``.
    """

    year: int
    month: int

    def __post_init__(self) -> None:
        """Validate the month number."""
        if not 1 <= self.month <= 12:
            raise ValueError(f"Invalid month: {self.month}")

    @classmethod
    def parse(cls, text: str) -> MonthlyPeriod:
        """Parse a ``YYYY-MM`` string.

        Raises
        ------
        ValueError
            If the text does not follow the ``YYYY-MM`` format.
        """
        match = _PERIOD_PATTERN.fullmatch(str(text).strip())
        if match is None:
            raise ValueError(f"Expected a 'YYYY-MM' period, got {text!r}")
        return cls(int(match["year"]), int(match["month"]))

    def shift(self, months: int) -> MonthlyPeriod:
        """Return the period ``months`` months later (or earlier)."""
        index = self.year * 12 + (self.month - 1) + months
        return MonthlyPeriod(index // 12, index % 12 + 1)

    def __str__(self) -> str:
        """Format the period as ``YYYY-MM``."""
        return f"{self.year:04d}-{self.month:02d}"


def month_range(start: str, end: str) -> list[str]:
    """Return every ``YYYY-MM`` period between two inclusive bounds.

    Raises
    ------
    ValueError
        If ``end`` precedes ``start``.
    """
    first, last = MonthlyPeriod.parse(start), MonthlyPeriod.parse(end)
    if last < first:
        raise ValueError(f"End period {end} precedes start period {start}")
    periods: list[str] = []
    current = first
    while current <= last:
        periods.append(str(current))
        current = current.shift(1)
    return periods


def validate_periods(
    periods: Iterable[str], *, require_contiguous: bool = True
) -> Sequence[str]:
    """Validate a sequence of periods.

    Parameters
    ----------
    periods : Iterable[str]
        Periods in ``YYYY-MM`` format.
    require_contiguous : bool, default True
        Whether the periods must be sorted, unique and without gaps.

    Returns
    -------
    Sequence[str]
        The validated periods as a list.

    Raises
    ------
    ValueError
        If a period is malformed, or the contiguity requirement fails.
    """
    values = [str(MonthlyPeriod.parse(p)) for p in periods]
    if not values:
        raise ValueError("Period sequence is empty")
    if require_contiguous:
        expected = month_range(values[0], values[-1])
        if values != expected:
            raise ValueError(
                "Periods are not sorted, unique and contiguous between "
                f"{values[0]} and {values[-1]}"
            )
    return values


def period_years(periods: pd.Series) -> pd.Series:
    """Extract the calendar year from a ``YYYY-MM`` period column."""
    return periods.astype(str).str.slice(0, 4).astype(int)
