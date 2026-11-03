"""Combine the reconstructed history with the observed GEIH series.

From the first observed month onward the GEIH values are used unchanged;
earlier months come from the reconstruction. Each row keeps its
provenance.
"""

from __future__ import annotations

import pandas as pd

from icml.domain.provenance import ProvenanceCategory
from icml.national.schema import (
    PERIOD_COLUMN,
    PROVENANCE_COLUMN,
    QUANTITY_COLUMNS,
)


class CombinationError(ValueError):
    """Raised when the history and the observed series cannot be joined."""


def _validated(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    missing = sorted({PERIOD_COLUMN, *QUANTITY_COLUMNS} - set(frame.columns))
    if missing:
        raise CombinationError(f"{name}: missing columns {missing}")
    data = frame[[PERIOD_COLUMN, *QUANTITY_COLUMNS]].copy()
    index = pd.PeriodIndex(data[PERIOD_COLUMN].astype(str), freq="M")
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise CombinationError(f"{name}: periods unsorted or duplicated")
    if not index.equals(pd.period_range(index[0], index[-1], freq="M")):
        raise CombinationError(f"{name}: periods have gaps")
    return data


def combine_history_with_observed(
    reconstructed: pd.DataFrame,
    observed: pd.DataFrame,
    *,
    history_provenance: ProvenanceCategory,
) -> pd.DataFrame:
    """Return the full monthly series with a provenance column.

    Parameters
    ----------
    reconstructed : pandas.DataFrame
        Reconstructed monthly series that starts before the observations.
    observed : pandas.DataFrame
        Observed monthly series (GEIH), used without modification.
    history_provenance : ProvenanceCategory
        Provenance assigned to the reconstructed months.

    Raises
    ------
    CombinationError
        If the history does not precede the observations or the combined
        series has gaps.
    """
    history = _validated(reconstructed, "reconstructed")
    current = _validated(observed, "observed")
    first_observed = current[PERIOD_COLUMN].iloc[0]
    if history[PERIOD_COLUMN].iloc[0] >= first_observed:
        raise CombinationError("No reconstructed months before observations")
    history = history[history[PERIOD_COLUMN] < first_observed]
    history.insert(1, PROVENANCE_COLUMN, str(history_provenance))
    current.insert(1, PROVENANCE_COLUMN, str(ProvenanceCategory.OBSERVED))
    combined = pd.concat([history, current], ignore_index=True)
    _validated(combined, "combined")
    return combined
