"""Reference national monthly series consumed by territorial stages.

Territorial stages (urban, departmental) use observed GEIH months as they
are published and, for the reconstructed history, the reconciled
(identity-consistent) series rather than the raw disaggregation, as in RC1.
"""

from __future__ import annotations

import pandas as pd

from icml.domain.provenance import ProvenanceCategory
from icml.national.schema import (
    PERIOD_COLUMN,
    PROVENANCE_COLUMN,
    QUANTITY_COLUMNS,
)


class ReferenceNationalError(ValueError):
    """Raised when the national artifacts cannot form the reference."""


def reference_national(
    combined: pd.DataFrame, reconciled: pd.DataFrame, last_period: str
) -> pd.DataFrame:
    """Return the national reference months up to ``last_period``.

    Parameters
    ----------
    combined : pandas.DataFrame
        ``national.combined_with_provenance`` artifact.
    reconciled : pandas.DataFrame
        ``national.reconciled_monthly`` artifact.
    last_period : str
        Last ``YYYY-MM`` period to keep.

    Raises
    ------
    ReferenceNationalError
        If reconstructed months do not precede the observed ones or the
        reconciled series does not cover them.
    """
    data = combined[combined[PERIOD_COLUMN] <= last_period].copy()
    history = data[PROVENANCE_COLUMN] != str(ProvenanceCategory.OBSERVED)
    observed_start = data.loc[~history, PERIOD_COLUMN].min()
    if not (data.loc[history, PERIOD_COLUMN] < observed_start).all():
        raise ReferenceNationalError(
            "Reconstructed months must precede observed GEIH months"
        )
    indexed = reconciled.set_index(PERIOD_COLUMN)
    missing = set(data.loc[history, PERIOD_COLUMN]) - set(indexed.index)
    if missing:
        raise ReferenceNationalError(
            f"Reconciled series misses {len(missing)} months"
        )
    replacement = indexed.loc[
        data.loc[history, PERIOD_COLUMN], list(QUANTITY_COLUMNS)
    ]
    data.loc[history, list(QUANTITY_COLUMNS)] = replacement.to_numpy()
    return data[[PERIOD_COLUMN, *QUANTITY_COLUMNS]].reset_index(drop=True)
