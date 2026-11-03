"""Monthly updates without rewriting published history.

Each cell of a product carries a revision state, and an update may only
change cells whose state allows it:

* ``definitivo``: the year has a published departmental anchor and the
  cell has been reconciled against it. An ordinary update never changes
  it.
* ``sujeto_a_ancla``: the national series and the city windows that
  determine the cell are closed, but its year has no published anchor
  yet. It changes when the anchor arrives.
* ``provisional``: the cell is inside the open 12-month rolling window,
  so the next month's windows still carry information about it. It
  changes every month.

The state depends only on dates: the last published month, the last year
with a departmental anchor and the window length. An update is accepted
when every change falls on cells the policy allows to change; otherwise
it is refused, naming the offending cells.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

STATE_FINAL = "definitivo"
STATE_PENDING_ANCHOR = "sujeto_a_ancla"
STATE_PROVISIONAL = "provisional"
MUTABLE: tuple[str, ...] = (STATE_PROVISIONAL, STATE_PENDING_ANCHOR)
_RELATIVE_TOLERANCE = 1e-9


class VintageError(ValueError):
    """Raised when an update would rewrite protected history."""


@dataclass(frozen=True)
class VintagePolicy:
    """Dates and rules that define the revision states.

    Attributes
    ----------
    last_month : str
        Last published month of this vintage (``YYYY-MM``).
    last_anchored_year : int
        Last year with a published departmental annex.
    window_length : int
        Months of the published rolling window.
    revise_open_window : bool
        Whether the months inside the open window may be revised (the
        project's choice) or are frozen once published.
    """

    last_month: str
    last_anchored_year: int
    window_length: int
    revise_open_window: bool = True


def revision_state(periods: pd.Series, policy: VintagePolicy) -> pd.Series:
    """Return the revision state of each period."""
    last = pd.Period(policy.last_month, freq="M")
    first_open = (
        str(last - (policy.window_length - 2))
        if policy.revise_open_window
        else str(last)
    )
    years = periods.str.slice(0, 4).astype(int)
    return pd.Series(
        np.where(
            periods >= first_open,
            STATE_PROVISIONAL,
            np.where(
                years > policy.last_anchored_year,
                STATE_PENDING_ANCHOR,
                STATE_FINAL,
            ),
        ),
        index=periods.index,
    )


def with_revision_state(
    product: pd.DataFrame, policy: VintagePolicy
) -> pd.DataFrame:
    """Add the ``revision_state`` column to a product."""
    result = product.copy()
    result["revision_state"] = revision_state(result["period"], policy)
    return result


@dataclass(frozen=True)
class UpdateReport:
    """What changed between two vintages of the same product."""

    changes: pd.DataFrame
    summary: dict[str, Any]

    @property
    def accepted(self) -> bool:
        """Whether every change fell on revisable cells."""
        return bool(self.summary["protected_cells_changed"] == 0)


def compare_vintages(
    previous: pd.DataFrame,
    current: pd.DataFrame,
    keys: Sequence[str],
    quantities: Sequence[str],
    policy: VintagePolicy,
) -> UpdateReport:
    """Compare two vintages cell by cell against the revision policy.

    ``previous`` must carry ``revision_state`` as published; the state of
    the previous vintage is what an update must respect.

    Raises
    ------
    VintageError
        If the previous vintage lacks its revision state, or the new one
        drops rows the old one had.
    """
    if "revision_state" not in previous.columns:
        raise VintageError("The previous vintage has no revision_state")
    current = current.drop(columns=["revision_state"], errors="ignore")
    merged = previous.merge(
        current,
        on=list(keys),
        how="left",
        suffixes=("_previous", "_current"),
        validate="one_to_one",
    )
    missing = merged[f"{quantities[0]}_current"].isna()
    if bool(missing.any()):
        raise VintageError(
            f"{int(missing.sum())} published rows are "
            "missing from the new vintage"
        )
    rows = []
    for quantity in quantities:
        before = np.array(merged[f"{quantity}_previous"], dtype=float)
        after = np.array(merged[f"{quantity}_current"], dtype=float)
        relative = np.abs(after - before) / np.maximum(np.abs(before), 1.0)
        frame = merged[list(keys)].copy()
        frame["quantity"] = quantity
        frame["revision_state"] = merged["revision_state"]
        frame["previous"] = before
        frame["current"] = after
        frame["relative_change"] = relative
        rows.append(frame[relative > _RELATIVE_TOLERANCE])
    changes = pd.concat(rows, ignore_index=True)
    protected = changes[changes["revision_state"] == STATE_FINAL]
    summary = {
        "cells_compared": int(len(merged) * len(quantities)),
        "cells_changed": int(len(changes)),
        "protected_cells_changed": int(len(protected)),
        "changed_by_state": {
            str(state): int(count)
            for state, count in changes["revision_state"]
            .value_counts()
            .items()
        },
        "max_relative_change_by_state": {
            str(state): float(group["relative_change"].max())
            for state, group in changes.groupby("revision_state")
        },
        "new_rows": int(len(current) - len(previous)),
    }
    return UpdateReport(changes=changes, summary=summary)


def apply_update(
    previous: pd.DataFrame,
    current: pd.DataFrame,
    keys: Sequence[str],
    policy: VintagePolicy,
) -> pd.DataFrame:
    """Graft a recomputed product onto a published vintage.

    Rows that were ``definitivo`` in the published vintage are kept whole
    and the rest are taken whole from the recomputation, so every row of
    the result comes from a single computation: its accounting
    identities, its factors and its national closure are internally
    consistent. Rows that did not exist before are added.

    Raises
    ------
    VintageError
        If the published vintage lacks its revision state, or the two
        vintages do not share their columns.
    """
    if "revision_state" not in previous.columns:
        raise VintageError("The previous vintage has no revision_state")
    recomputed = current.drop(columns=["revision_state"], errors="ignore")
    published = previous.drop(columns=["revision_state"])
    if list(published.columns) != list(recomputed.columns):
        raise VintageError("The two vintages have different columns")
    frozen_keys = pd.MultiIndex.from_frame(
        previous.loc[previous["revision_state"] == STATE_FINAL, list(keys)]
    )
    frozen = pd.MultiIndex.from_frame(published[list(keys)]).isin(frozen_keys)
    fresh = ~pd.MultiIndex.from_frame(recomputed[list(keys)]).isin(frozen_keys)
    result = (
        pd.concat([published[frozen], recomputed[fresh]], ignore_index=True)
        .sort_values(list(keys))
        .reset_index(drop=True)
    )
    result["revision_state"] = revision_state(result["period"], policy)
    return result


def assert_accepted(report: UpdateReport) -> None:
    """Refuse an update that rewrote final cells.

    Raises
    ------
    VintageError
        If any cell in ``definitivo`` state changed.
    """
    if not report.accepted:
        protected = report.changes[
            report.changes["revision_state"] == STATE_FINAL
        ]
        sample = protected.head(5).to_dict("records")
        raise VintageError(
            f"{len(protected)} final cells changed; examples: {sample}"
        )
