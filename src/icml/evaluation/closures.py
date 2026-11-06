"""Closure variants compared by the transfer evaluation.

* ``rc1``: the published hierarchical closure (all six quantities add to
  the national GEIH totals; anchors exact; the universe gap falls on the
  unanchored territories).
* ``uniform_raking`` (A): one factor per month and quantity scales all 33
  territories to the national GEIH totals; anchors move by that factor.
* ``demographic_universe`` (B): the RC1 closure, but national totals are
  first scaled to the sum of departmental demographic projections; the
  national rates apply to the wider universe and anchors stay exact. The
  departmental sum no longer equals the published national total.
* ``components_only`` (C): the RC1 closure for employed, unemployed and
  inactive; labor population is not reconciled.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

import numpy as np
import pandas as pd

from icml.reconciliation.hierarchical import (
    HierarchicalPolicy,
    HierarchicalReconciler,
)

COMPONENTS: tuple[str, ...] = ("employed", "unemployed", "inactive")
SCALED: tuple[str, ...] = (
    *COMPONENTS,
    "labor_force",
    "working_age",
    "population",
)


class Closure(Protocol):
    """A closure variant: model panel in, closed panel out."""

    def apply(
        self,
        panel: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> pd.DataFrame:
        """Return the closed panel with ``labor_population_reconciled``."""


class RC1Closure:
    """The published hierarchical closure."""

    def __init__(self, policy: HierarchicalPolicy) -> None:
        """Compose the reconciler."""
        self._reconciler = HierarchicalReconciler(policy)

    def apply(
        self,
        panel: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> pd.DataFrame:
        """Run the RC1 closure."""
        return self._reconciler.run(panel, national, anchors).panel


class DemographicUniverseClosure:
    """RC1 closure with national totals scaled to the demographic sum.

    Scaling the totals changes the conditioning of the KKT systems: an
    annual population anchor of Valle (4.5 million people) was kept to
    1.007e-4 persons, just above RC1's 1e-4 check. The anchor check is
    therefore 1e-3 persons here (2e-10 relative); it is solver precision,
    not a methodological tolerance.
    """

    ANCHOR_TOLERANCE_PERSONS = 1e-3

    def __init__(self, policy: HierarchicalPolicy) -> None:
        """Compose the reconciler with the solver-precision check."""
        self._reconciler = HierarchicalReconciler(
            replace(
                policy,
                anchor_tolerance_persons=max(
                    policy.anchor_tolerance_persons,
                    self.ANCHOR_TOLERANCE_PERSONS,
                ),
            )
        )

    def apply(
        self,
        panel: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> pd.DataFrame:
        """Scale every national quantity by the universe ratio, then close."""
        demographic = panel.groupby("period")[
            "population_demographic_projection"
        ].sum()
        scaled = national.copy()
        ratio = np.array(
            demographic.loc[scaled["period"]], dtype=float
        ) / np.array(scaled["population"], dtype=float)
        for column in SCALED:
            scaled[column] = np.array(scaled[column], dtype=float) * ratio
        return self._reconciler.run(panel, scaled, anchors).panel


class ComponentsOnlyClosure:
    """RC1 closure without reconciling labor population."""

    def __init__(self, policy: HierarchicalPolicy) -> None:
        """Compose the reconciler without the population leg."""
        self._reconciler = HierarchicalReconciler(
            policy, reconcile_population=False
        )

    def apply(
        self,
        panel: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> pd.DataFrame:
        """Run the closure on labor components only."""
        return self._reconciler.run(panel, national, anchors).panel


class UniformRakingClosure:
    """Scale all territories by one factor per month and quantity."""

    def apply(
        self,
        panel: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> pd.DataFrame:
        """Rake components and population; derive aggregates."""
        result = panel.copy()
        reference = national.set_index("period")
        for column in COMPONENTS:
            totals = result.groupby("period")[column].transform("sum")
            target = np.array(
                reference.loc[result["period"], column], dtype=float
            )
            result[column] = (
                np.array(result[column]) * target / np.array(totals)
            )
        totals = result.groupby("period")[
            "population_demographic_projection"
        ].transform("sum")
        target = np.array(
            reference.loc[result["period"], "population"], dtype=float
        )
        result["labor_population_reconciled"] = (
            np.array(result["population_demographic_projection"], dtype=float)
            * target
            / np.array(totals)
        )
        result["labor_force"] = result["employed"] + result["unemployed"]
        result["working_age"] = result["labor_force"] + result["inactive"]
        return result


def build_closures(
    names: list[str] | tuple[str, ...], policy: HierarchicalPolicy
) -> dict[str, Closure]:
    """Instantiate the requested closure variants.

    Raises
    ------
    ValueError
        On an unknown variant name.
    """
    factories: dict[str, Callable[[], Closure]] = {
        "rc1": lambda: RC1Closure(policy),
        "uniform_raking": UniformRakingClosure,
        "demographic_universe": lambda: DemographicUniverseClosure(policy),
        "components_only": lambda: ComponentsOnlyClosure(policy),
    }
    unknown = set(names) - set(factories)
    if unknown:
        raise ValueError(f"Unknown closure variants: {sorted(unknown)}")
    return {name: factories[name]() for name in names}
