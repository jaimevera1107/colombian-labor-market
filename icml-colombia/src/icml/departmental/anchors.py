"""Annual anchor closure and demographic comparison.

Published departmental anchors carry rounding; labor force and working age
are recomputed from their components. The change must stay within the
publication rounding, otherwise the source is inconsistent and the stage
stops. GEIH population is compared with, never replaced by, the
demographic projections.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from icml.domain.quantities import LaborQuantity

QUANTITIES: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
    "population",
)


class AnchorError(ValueError):
    """Raised when official anchors are inconsistent beyond rounding."""


@dataclass(frozen=True)
class AnchorPolicy:
    """Anchor closure and projection settings."""

    max_closure_change_persons: float
    projection_area_type: str


def close_annual_anchors(
    official: pd.DataFrame, policy: AnchorPolicy
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Recompute derived quantities and trace every change.

    Raises
    ------
    AnchorError
        If a change exceeds the rounding limit, or levels become negative
        or working age exceeds population.
    """
    closed = official.copy()
    closed["labor_force"] = closed["employed"] + closed["unemployed"]
    closed["working_age"] = closed["labor_force"] + closed["inactive"]
    trace = []
    for quantity in QUANTITIES:
        before = np.array(official[quantity], dtype=float)
        after = np.array(closed[quantity], dtype=float)
        change = after - before
        relative = np.divide(
            100 * change,
            before,
            out=np.full_like(change, np.nan),
            where=before != 0,
        )
        trace.append(
            pd.DataFrame(
                {
                    "dep_code": official["dep_code"].astype(int).to_numpy(),
                    "year": official["year"].astype(int).to_numpy(),
                    "quantity": quantity,
                    "official_value": before,
                    "closed_value": after,
                    "change_persons": change,
                    "relative_change_pct": relative,
                }
            )
        )
    corrections = pd.concat(trace, ignore_index=True)
    if (
        corrections["change_persons"].abs().max()
        > policy.max_closure_change_persons
    ):
        raise AnchorError("Closure changed an anchor beyond rounding")
    if (closed[list(QUANTITIES)] < 0).any().any() or (
        closed["working_age"] > closed["population"]
    ).any():
        raise AnchorError("Inconsistent anchors after closure")
    return closed, corrections


def annual_projections(
    projections: pd.DataFrame, territory_codes: set[int], policy: AnchorPolicy
) -> pd.DataFrame:
    """Return total demographic projections per territory and year.

    Raises
    ------
    AnchorError
        If a territory is missing or a key is duplicated.
    """
    total = projections.loc[
        projections["area_type"] == policy.projection_area_type,
        ["dep_code", "dep_name", "year", "population"],
    ].copy()
    if (
        total.duplicated(subset=["dep_code", "year"]).any()
        or set(total["dep_code"]) != territory_codes
    ):
        raise AnchorError("Demographic projections incomplete or duplicated")
    return total.rename(
        columns={"population": "population_demographic_projection"}
    ).reset_index(drop=True)


def compare_population(
    official: pd.DataFrame, projections: pd.DataFrame
) -> pd.DataFrame:
    """Compare GEIH annual population with the demographic projection.

    Raises
    ------
    AnchorError
        If an observed department-year lacks a projection.
    """
    population = str(LaborQuantity.POPULATION)
    merged = official[["dep_code", "department", "year", population]].merge(
        projections[["dep_code", "year", "population_demographic_projection"]],
        on=["dep_code", "year"],
        how="left",
        validate="one_to_one",
    )
    if merged["population_demographic_projection"].isna().any():
        raise AnchorError("Missing projection for an observed year")
    merged["gap_persons"] = (
        merged[population] - merged["population_demographic_projection"]
    )
    merged["gap_pct"] = (
        100
        * merged["gap_persons"]
        / merged["population_demographic_projection"]
    )
    return merged
