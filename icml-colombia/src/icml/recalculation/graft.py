"""Graft frozen years from the published vintage onto a recomputation.

Whole rows are taken, never single cells, so each row keeps the identities,
factors and national closure of one computation (same argument as
``icml.pipeline.vintage``). Frozen years come from the published vintage;
the open years come from the recomputation.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from icml.recalculation.policy import AnchorPolicy

DEFAULT_TOLERANCE = 1e-6


def _year(periods: pd.Series) -> pd.Series:
    return periods.astype(str).str[:4].astype(int)


def graft_frozen_years(
    published: pd.DataFrame,
    recomputed: pd.DataFrame,
    policy: AnchorPolicy,
    *,
    keys: Sequence[str],
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[pd.DataFrame, dict]:
    """Keep the published rows of frozen years and the recomputed others.

    Parameters
    ----------
    published, recomputed : pandas.DataFrame
        Same columns; both carry a ``period`` column (``YYYY-MM``).
    policy : AnchorPolicy
        Decides which years are frozen.
    keys : Sequence[str]
        Columns that identify a row, including ``period``.
    tolerance : float
        Absolute tolerance used to measure what a recomputation would have
        changed in the frozen years (diagnostic only).

    Returns
    -------
    tuple[pandas.DataFrame, dict]
        The grafted table (published column order) and a report.

    Raises
    ------
    ValueError
        If the columns differ, keys are duplicated, or the published table
        does not cover a frozen period that the recomputation has.
    """
    if list(published.columns) != list(recomputed.columns):
        raise ValueError("Published and recomputed tables have different columns")
    for name, frame in (("published", published), ("recomputed", recomputed)):
        if frame.duplicated(list(keys)).any():
            raise ValueError(f"Duplicated keys in the {name} table")

    published_frozen = published[policy.last_anchor_year >= _year(published["period"])]
    recomputed_frozen = recomputed[policy.last_anchor_year >= _year(recomputed["period"])]
    recomputed_open = recomputed[policy.last_anchor_year < _year(recomputed["period"])]

    missing = recomputed_frozen.merge(
        published_frozen[list(keys)], on=list(keys), how="left", indicator=True
    )
    absent = int((missing["_merge"] == "left_only").sum())
    if absent:
        raise ValueError(
            f"{absent} frozen rows exist in the recomputation but not in the "
            "published vintage; a new territory or month in a frozen year "
            "needs a total recalculation"
        )

    grafted = pd.concat([published_frozen, recomputed_open], ignore_index=True)
    grafted = grafted.sort_values(list(keys), kind="stable").reset_index(drop=True)

    merged = published_frozen.merge(
        recomputed_frozen, on=list(keys), suffixes=("_pub", "_new")
    )
    changed = 0
    for column in published.columns:
        if column in keys:
            continue
        old, new = merged[f"{column}_pub"], merged[f"{column}_new"]
        old_n = pd.to_numeric(old, errors="coerce")
        new_n = pd.to_numeric(new, errors="coerce")
        numeric = old_n.notna() & new_n.notna()
        differs = pd.Series(False, index=merged.index)
        differs[numeric] = (old_n[numeric] - new_n[numeric]).abs() > tolerance
        differs[~numeric] = old[~numeric].astype(str) != new[~numeric].astype(str)
        changed += int(differs.sum())
    report = {
        "frozen_through_year": policy.last_anchor_year,
        "rows_frozen_from_published": int(len(published_frozen)),
        "rows_open_from_recomputation": int(len(recomputed_open)),
        "frozen_cells_a_recomputation_would_have_changed": changed,
        "frozen_cells_changed_in_output": 0,
    }
    return grafted, report


def assert_frozen_unchanged(
    published: pd.DataFrame,
    grafted: pd.DataFrame,
    policy: AnchorPolicy,
    *,
    keys: Sequence[str],
) -> None:
    """Fail if any frozen row of ``grafted`` differs from ``published``."""
    old = published[policy.last_anchor_year >= _year(published["period"])]
    new = grafted[policy.last_anchor_year >= _year(grafted["period"])]
    old = old.sort_values(list(keys), kind="stable").reset_index(drop=True)
    new = new.sort_values(list(keys), kind="stable").reset_index(drop=True)
    if not old.astype(str).equals(new.astype(str)):
        raise AssertionError("A frozen row changed during the graft")
    if np.size(old) == 0:
        raise AssertionError("No frozen rows were compared")
