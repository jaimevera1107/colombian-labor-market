"""Labor-market quantities, accounting identities and derived rates.

The identities below are the hard accounting contract of every ICML
product::

    labor_force = employed + unemployed
    working_age = labor_force + inactive
    0 <= working_age <= population

All levels are expressed in persons.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum, StrEnum

import numpy as np
import pandas as pd


class LaborQuantity(StrEnum):
    """Canonical names of the six primitive labor quantities."""

    POPULATION = "population"
    WORKING_AGE = "working_age"
    LABOR_FORCE = "labor_force"
    EMPLOYED = "employed"
    UNEMPLOYED = "unemployed"
    INACTIVE = "inactive"


LABOR_QUANTITIES: tuple[LaborQuantity, ...] = tuple(LaborQuantity)

# Legacy RC1 column names mapped to canonical quantity names. National and
# urban RC1 tables use English names with Spanish acronyms; departmental
# tables use Spanish names. The mapping is explicit so that regression
# comparisons against RC1 never rely on implicit renaming.
LEGACY_COLUMN_MAP: Mapping[str, LaborQuantity] = {
    "population": LaborQuantity.POPULATION,
    "pet": LaborQuantity.WORKING_AGE,
    "pea": LaborQuantity.LABOR_FORCE,
    "employed": LaborQuantity.EMPLOYED,
    "unemployed": LaborQuantity.UNEMPLOYED,
    "inactive": LaborQuantity.INACTIVE,
    "ocupados": LaborQuantity.EMPLOYED,
    "desocupados": LaborQuantity.UNEMPLOYED,
    "inactivos": LaborQuantity.INACTIVE,
    "poblacion_laboral_conciliada": LaborQuantity.POPULATION,
}


class RateScale(Enum):
    """Scale in which derived rates are expressed.

    RC1 national tables use percentages, while departmental tables use
    fractions. The scale is therefore always explicit.
    """

    FRACTION = 1.0
    PERCENT = 100.0


@dataclass(frozen=True)
class IdentityReport:
    """Result of checking the labor accounting identities.

    Attributes
    ----------
    max_labor_force_residual : float
        Largest ``|labor_force - employed - unemployed|`` in persons.
    max_working_age_residual : float
        Largest ``|working_age - labor_force - inactive|`` in persons.
    negative_level_rows : int
        Rows with at least one negative level.
    working_age_above_population_rows : int
        Rows where working-age population exceeds total population by more
        than the tolerance. Zero when population is not checked.
    tolerance_persons : float
        Absolute tolerance used for every check.
    """

    max_labor_force_residual: float
    max_working_age_residual: float
    negative_level_rows: int
    working_age_above_population_rows: int
    tolerance_persons: float

    @property
    def passed(self) -> bool:
        """Return whether every identity holds within tolerance."""
        return (
            self.max_labor_force_residual <= self.tolerance_persons
            and self.max_working_age_residual <= self.tolerance_persons
            and self.negative_level_rows == 0
            and self.working_age_above_population_rows == 0
        )


def _require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"Missing required columns: {missing}")


def _as_float_array(frame: pd.DataFrame, column: str) -> np.ndarray:
    # ``np.array`` (not ``to_numpy``) guarantees a writable copy, which keeps
    # the code independent of pandas copy-on-write semantics.
    return np.array(frame[column], dtype=float)


def check_labor_identities(
    frame: pd.DataFrame,
    *,
    tolerance_persons: float,
    check_population: bool = True,
) -> IdentityReport:
    """Check the accounting identities on a table of labor levels.

    Parameters
    ----------
    frame : pandas.DataFrame
        Table with canonical quantity columns (see :class:`LaborQuantity`).
    tolerance_persons : float
        Non-negative absolute tolerance in persons.
    check_population : bool, default True
        Whether to require ``working_age <= population``. Disable it for
        tables that do not carry a population column.

    Returns
    -------
    IdentityReport
        Maximum residuals and violation counts.

    Raises
    ------
    ValueError
        If the tolerance is negative or the frame is empty.
    KeyError
        If a required column is missing.
    """
    if tolerance_persons < 0:
        raise ValueError("tolerance_persons must be non-negative")
    if frame.empty:
        raise ValueError("Cannot check identities on an empty table")

    required = [
        LaborQuantity.WORKING_AGE,
        LaborQuantity.LABOR_FORCE,
        LaborQuantity.EMPLOYED,
        LaborQuantity.UNEMPLOYED,
        LaborQuantity.INACTIVE,
    ]
    if check_population:
        required.append(LaborQuantity.POPULATION)
    _require_columns(frame, [str(column) for column in required])

    levels = {q: _as_float_array(frame, q) for q in required}
    labor_force_residual = np.abs(
        levels[LaborQuantity.LABOR_FORCE]
        - levels[LaborQuantity.EMPLOYED]
        - levels[LaborQuantity.UNEMPLOYED]
    )
    working_age_residual = np.abs(
        levels[LaborQuantity.WORKING_AGE]
        - levels[LaborQuantity.LABOR_FORCE]
        - levels[LaborQuantity.INACTIVE]
    )
    stacked = np.vstack(list(levels.values()))
    negative_rows = int(np.any(stacked < -tolerance_persons, axis=0).sum())

    above_population = 0
    if check_population:
        excess = (
            levels[LaborQuantity.WORKING_AGE]
            - levels[LaborQuantity.POPULATION]
        )
        above_population = int((excess > tolerance_persons).sum())

    return IdentityReport(
        max_labor_force_residual=float(np.nanmax(labor_force_residual)),
        max_working_age_residual=float(np.nanmax(working_age_residual)),
        negative_level_rows=negative_rows,
        working_age_above_population_rows=above_population,
        tolerance_persons=tolerance_persons,
    )


def _safe_ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    """Divide element-wise, returning NaN where the denominator is <= 0."""
    result = np.full(numerator.shape, np.nan, dtype=float)
    valid = denominator > 0
    np.divide(numerator, denominator, out=result, where=valid)
    return result


def compute_labor_rates(
    frame: pd.DataFrame, *, scale: RateScale
) -> pd.DataFrame:
    """Compute the standard labor rates from canonical levels.

    Parameters
    ----------
    frame : pandas.DataFrame
        Table with ``working_age``, ``labor_force``, ``employed``,
        ``unemployed`` and ``inactive`` columns.
    scale : RateScale
        Whether rates are returned as fractions or percentages.

    Returns
    -------
    pandas.DataFrame
        New frame (same index) with ``unemployment_rate``,
        ``employment_rate``, ``participation_rate`` and ``inactivity_rate``.
        Rates are NaN when their denominator is not positive.
    """
    _require_columns(
        frame,
        [
            LaborQuantity.WORKING_AGE,
            LaborQuantity.LABOR_FORCE,
            LaborQuantity.EMPLOYED,
            LaborQuantity.UNEMPLOYED,
            LaborQuantity.INACTIVE,
        ],
    )
    working_age = _as_float_array(frame, LaborQuantity.WORKING_AGE)
    labor_force = _as_float_array(frame, LaborQuantity.LABOR_FORCE)
    factor = scale.value
    rates = {
        "unemployment_rate": _safe_ratio(
            _as_float_array(frame, LaborQuantity.UNEMPLOYED), labor_force
        ),
        "employment_rate": _safe_ratio(
            _as_float_array(frame, LaborQuantity.EMPLOYED), working_age
        ),
        "participation_rate": _safe_ratio(labor_force, working_age),
        "inactivity_rate": _safe_ratio(
            _as_float_array(frame, LaborQuantity.INACTIVE), working_age
        ),
    }
    return pd.DataFrame(
        {name: values * factor for name, values in rates.items()},
        index=frame.index,
    )


def to_canonical_columns(
    frame: pd.DataFrame,
    column_map: Mapping[str, LaborQuantity] = LEGACY_COLUMN_MAP,
) -> pd.DataFrame:
    """Rename legacy quantity columns to canonical names.

    Parameters
    ----------
    frame : pandas.DataFrame
        Table with legacy column names.
    column_map : Mapping[str, LaborQuantity], optional
        Legacy-to-canonical mapping. Only columns present are renamed.

    Returns
    -------
    pandas.DataFrame
        Copy of the table with canonical names.

    Raises
    ------
    ValueError
        If two legacy columns map to the same canonical quantity, which
        would silently drop data.
    """
    present = {
        legacy: str(canonical)
        for legacy, canonical in column_map.items()
        if legacy in frame.columns
    }
    targets = list(present.values())
    duplicated = sorted({t for t in targets if targets.count(t) > 1})
    if duplicated:
        raise ValueError(
            f"Ambiguous legacy columns map to the same quantity: {duplicated}"
        )
    return frame.rename(columns=present)
