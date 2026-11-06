"""Accounting contracts that depend on the provenance of each value.

Published DANE figures are rounded, so observed rows may violate the
identities by up to the publication rounding, while every estimated value
must satisfy them to numerical precision. RC1 documents this explicitly
and never alters observed figures to force equality.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from icml.domain.provenance import ProvenanceCategory, resolve_legacy_labels
from icml.domain.quantities import IdentityReport, check_labor_identities


@dataclass(frozen=True)
class IdentityPolicy:
    """Identity tolerances by provenance (no implicit defaults).

    Attributes
    ----------
    observed_tolerance_persons : float
        Allowed residual for published observations (rounding).
    estimated_tolerance_persons : float
        Allowed residual for every estimated value.
    """

    observed_tolerance_persons: float
    estimated_tolerance_persons: float

    def __post_init__(self) -> None:
        """Reject negative tolerances."""
        if (
            min(
                self.observed_tolerance_persons,
                self.estimated_tolerance_persons,
            )
            < 0
        ):
            raise ValueError("Identity tolerances must be non-negative")

    def tolerance_for(self, category: ProvenanceCategory) -> float:
        """Return the tolerance that applies to a provenance category."""
        if category is ProvenanceCategory.OBSERVED:
            return self.observed_tolerance_persons
        return self.estimated_tolerance_persons


def check_identities_by_provenance(
    frame: pd.DataFrame,
    *,
    provenance_column: str,
    policy: IdentityPolicy,
    check_population: bool = True,
) -> Mapping[ProvenanceCategory, IdentityReport]:
    """Check identities separately for each provenance category.

    Parameters
    ----------
    frame : pandas.DataFrame
        Canonical levels plus a column of legacy provenance labels.
    provenance_column : str
        Column holding the RC1 origin labels.
    policy : IdentityPolicy
        Tolerances by provenance.
    check_population : bool, default True
        Whether to also require ``working_age <= population``.

    Returns
    -------
    Mapping[ProvenanceCategory, IdentityReport]
        One report per category present in the table.

    Raises
    ------
    KeyError
        If the provenance column is missing or holds unknown labels.
    """
    if provenance_column not in frame.columns:
        raise KeyError(f"Missing provenance column: {provenance_column}")
    labels = frame[provenance_column].astype(str)
    resolved = resolve_legacy_labels(labels)
    categories = labels.map({k: v.category for k, v in resolved.items()})
    reports: dict[ProvenanceCategory, IdentityReport] = {}
    for category in sorted(set(categories)):
        subset = frame.loc[categories == category]
        reports[category] = check_labor_identities(
            subset,
            tolerance_persons=policy.tolerance_for(category),
            check_population=check_population,
        )
    return reports
