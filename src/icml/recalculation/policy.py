"""Which periods are frozen: every year covered by the departmental annex.

The departmental annex is the anchor of the whole system. A year that it
covers is **final**: an ordinary (anchored) recalculation never changes it,
not even the months that an open rolling window still touches. The years
after the last anchor year stay open until the next annex is published.
Only an explicit total recalculation rewrites a frozen year.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from icml.domain.periods import MonthlyPeriod

ANCHORED = "anclado"
TOTAL = "total"
MODES: tuple[str, str] = (ANCHORED, TOTAL)


@dataclass(frozen=True)
class AnchorPolicy:
    """Frozen/open split of a calendar.

    Attributes
    ----------
    last_anchor_year : int
        Last year covered by the departmental annex (2025 in H36).
    """

    last_anchor_year: int

    def __post_init__(self) -> None:
        """Validate the year."""
        if not 1993 <= self.last_anchor_year <= 2100:
            raise ValueError(f"Implausible anchor year: {self.last_anchor_year}")

    def is_frozen(self, period: str) -> bool:
        """Return True if the month belongs to an anchored (final) year."""
        return MonthlyPeriod.parse(period).year <= self.last_anchor_year

    def split(self, periods: Iterable[str]) -> tuple[list[str], list[str]]:
        """Return ``(frozen, open)`` periods, each in the input order."""
        frozen: list[str] = []
        opened: list[str] = []
        for period in periods:
            (frozen if self.is_frozen(period) else opened).append(period)
        return frozen, opened

    def advanced_to(self, year: int) -> AnchorPolicy:
        """Return the policy after a new annex covers ``year``.

        Raises
        ------
        ValueError
            If ``year`` does not move the anchor forward.
        """
        if year <= self.last_anchor_year:
            raise ValueError(
                f"Anchor can only advance: {year} <= {self.last_anchor_year}"
            )
        return AnchorPolicy(year)


def anchor_year_from_years(years: Iterable[int]) -> int:
    """Return the last year present in a departmental annex."""
    values = sorted({int(year) for year in years})
    if not values:
        raise ValueError("The departmental annex has no years")
    return values[-1]
