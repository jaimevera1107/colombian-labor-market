"""Accounting reconciliation of the national annual anchors and months.

Historical (pre-GEIH) annual anchors are estimated independently for each
quantity and do not satisfy the identities. They are projected onto the
identity-consistent subspace by weighted least squares, where each anchor
has an assumed relative uncertainty. Observed GEIH years are not modified;
only their derived quantities are recomputed from the base components to
remove publication rounding. Monthly series are then rescaled
proportionally to the reconciled annual means.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from icml.national.schema import (
    BASE_QUANTITIES,
    PERIOD_COLUMN,
    YEAR_COLUMN,
)

# Order of the six quantities in the identity system below.
RECONCILED_QUANTITIES: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "population",
    "labor_force",
    "working_age",
)
# Maps the four free components (employed, unemployed, inactive,
# population) onto the six quantities:
#   labor_force = employed + unemployed
#   working_age = employed + unemployed + inactive
IDENTITY_MATRIX = np.array(
    [
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 1, 0],
        [0, 0, 0, 1],
        [1, 1, 0, 0],
        [1, 1, 1, 0],
    ],
    dtype=float,
)
_ANNUAL_PRESERVATION_TOLERANCE = 1e-6
_POPULATION_TOLERANCE = 1e-7


class ReconciliationError(ValueError):
    """Raised when reconciliation cannot satisfy its constraints."""


@dataclass(frozen=True)
class ReconciliationPolicy:
    """Reconciliation settings and review thresholds.

    Attributes
    ----------
    historical_end : int
        Last year whose anchors are estimates (later years are observed).
    anchor_relative_sigma : float
        Assumed relative standard error of historical anchors.
    minimum_anchor_sigma_persons : float
        Floor of the assumed standard error, in persons.
    max_observed_rounding_persons : float
        Largest identity residual accepted in observed years.
    max_annual_relative_shift : float
        Review threshold for annual changes (reported).
    max_monthly_relative_shift : float
        Review threshold for monthly changes (reported).
    max_added_bridge_log_shift : float
        Hard gate: extra log change added at the 2000-2001 seam.
    """

    historical_end: int
    anchor_relative_sigma: float
    minimum_anchor_sigma_persons: float
    max_observed_rounding_persons: float
    max_annual_relative_shift: float
    max_monthly_relative_shift: float
    max_added_bridge_log_shift: float


def with_derived_quantities(frame: pd.DataFrame) -> pd.DataFrame:
    """Recompute labor force and working age from their components."""
    result = frame.copy()
    result["labor_force"] = result["employed"] + result["unemployed"]
    result["working_age"] = result["labor_force"] + result["inactive"]
    return result


@dataclass(frozen=True)
class ReconciliationResult:
    """Reconciled anchors and months with their audit trail."""

    annual: pd.DataFrame
    monthly: pd.DataFrame
    annual_adjustments: pd.DataFrame
    monthly_factors: pd.DataFrame
    monthly_differences: pd.DataFrame
    seam_continuity: pd.DataFrame
    gates: Mapping[str, bool]
    review_flags: Mapping[str, bool]


class NationalReconciler:
    """Close the accounting identities of the national reconstruction."""

    def __init__(self, policy: ReconciliationPolicy) -> None:
        """Store the policy."""
        self._policy = policy

    def reconcile_annual(
        self, annual: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Reconcile annual anchors.

        Returns
        -------
        tuple[pandas.DataFrame, pandas.DataFrame]
            Reconciled anchors and one audit row per year and quantity.

        Raises
        ------
        ReconciliationError
            On missing years, non-finite values, observed years outside the
            rounding tolerance, or a WLS solution violating positivity.
        """
        source = annual.set_index(YEAR_COLUMN).sort_index()
        years = list(source.index)
        if source.index.has_duplicates or years != list(
            range(int(min(years)), int(max(years)) + 1)
        ):
            raise ReconciliationError("Anchor years missing or duplicated")
        values = np.array(source[list(RECONCILED_QUANTITIES)], dtype=float)
        if not np.isfinite(values).all():
            raise ReconciliationError("Non-finite anchors")

        result = source.copy()
        audit: list[dict[str, object]] = []
        for position, year in enumerate(years):
            original = values[position]
            row = source.loc[year]
            if year > self._policy.historical_end:
                reconciled = self._derive_observed(year, row)
                origin = "observed_source_kept_derived_recomputed"
            else:
                reconciled = self._weighted_projection(year, original)
                origin = "historical_anchor_wls"
            result.loc[year, list(RECONCILED_QUANTITIES)] = reconciled
            for quantity, before, after in zip(
                RECONCILED_QUANTITIES, original, reconciled, strict=True
            ):
                audit.append(
                    {
                        YEAR_COLUMN: int(year),
                        "quantity": quantity,
                        "original": float(before),
                        "reconciled": float(after),
                        "delta_persons": float(after - before),
                        "relative_change": float(after / before - 1),
                        "origin": origin,
                    }
                )
        return result.reset_index(), pd.DataFrame(audit)

    def _derive_observed(self, year: int, row: pd.Series) -> np.ndarray:
        gap = max(
            abs(row["labor_force"] - row["employed"] - row["unemployed"]),
            abs(row["working_age"] - row["labor_force"] - row["inactive"]),
        )
        if gap > self._policy.max_observed_rounding_persons:
            raise ReconciliationError(
                f"Observed GEIH year {year} exceeds rounding tolerance"
            )
        components = np.array(row[list(BASE_QUANTITIES)], dtype=float)
        return np.asarray(IDENTITY_MATRIX @ components)

    def _weighted_projection(
        self, year: int, original: np.ndarray
    ) -> np.ndarray:
        sigma = np.maximum(
            np.abs(original) * self._policy.anchor_relative_sigma,
            self._policy.minimum_anchor_sigma_persons,
        )
        components = np.linalg.lstsq(
            IDENTITY_MATRIX / sigma[:, None], original / sigma, rcond=None
        )[0]
        employed, unemployed, inactive, population = components
        if (components <= 0).any() or population < (
            employed + unemployed + inactive
        ):
            raise ReconciliationError(
                f"WLS solution needs active constraints in {year}"
            )
        return np.asarray(IDENTITY_MATRIX @ components)

    def reconcile_monthly(
        self, monthly: pd.DataFrame, annual: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Rescale monthly components to the reconciled annual means.

        Raises
        ------
        ReconciliationError
            On incomplete years, non-positive values, working age above
            population, or annual means not preserved.
        """
        data = monthly.copy()
        data[PERIOD_COLUMN] = data[PERIOD_COLUMN].astype(str)
        if data[PERIOD_COLUMN].duplicated().any():
            raise ReconciliationError("Duplicated months")
        year = data[PERIOD_COLUMN].str.slice(0, 4).astype(int)
        targets = annual.set_index(YEAR_COLUMN)
        if sorted(year.unique().tolist()) != targets.index.tolist():
            raise ReconciliationError("Monthly and annual years differ")
        if (year.value_counts() != 12).any():
            raise ReconciliationError("Incomplete years")
        if (data[list(BASE_QUANTITIES)] <= 0).any().any():
            raise ReconciliationError("Non-positive base quantities")

        adjusted = data.copy()
        factors: list[dict[str, object]] = []
        for current_year, index in data.groupby(year).groups.items():
            for quantity in BASE_QUANTITIES:
                expected = float(targets.loc[current_year, quantity])
                observed = float(data.loc[index, quantity].mean())
                factor = expected / observed
                adjusted.loc[index, quantity] = (
                    data.loc[index, quantity] * factor
                )
                factors.append(
                    {
                        YEAR_COLUMN: int(current_year),
                        "quantity": quantity,
                        "factor": factor,
                        "annual_mean_before": observed,
                        "annual_mean_after": float(
                            adjusted.loc[index, quantity].mean()
                        ),
                        "target": expected,
                    }
                )
        adjusted = with_derived_quantities(adjusted)
        levels = adjusted[list(RECONCILED_QUANTITIES)]
        if (levels <= 0).any().any() or (
            adjusted["working_age"]
            > adjusted["population"] + _POPULATION_TOLERANCE
        ).any():
            raise ReconciliationError(
                "Monthly closure needs an inequality projection"
            )
        means = levels.groupby(year).mean()
        gap = np.abs(means - targets[list(RECONCILED_QUANTITIES)]).max().max()
        if gap > _ANNUAL_PRESERVATION_TOLERANCE:
            raise ReconciliationError("Annual means not preserved")
        return adjusted, pd.DataFrame(factors)

    def run(
        self, annual: pd.DataFrame, monthly: pd.DataFrame
    ) -> ReconciliationResult:
        """Reconcile anchors and months and evaluate the stage gates.

        Raises
        ------
        ReconciliationError
            If a hard gate fails (RC1 aborts the stage in that case).
        """
        reconciled_annual, adjustments = self.reconcile_annual(annual)
        reconciled_monthly, factors = self.reconcile_monthly(
            monthly, reconciled_annual
        )
        differences = self._monthly_differences(monthly, reconciled_monthly)
        seam = self._seam_continuity(
            annual, reconciled_annual, monthly, reconciled_monthly
        )
        gates, flags = self._evaluate(
            reconciled_annual,
            reconciled_monthly,
            adjustments,
            differences,
            seam,
        )
        if not all(gates.values()):
            failed = sorted(k for k, v in gates.items() if not v)
            raise ReconciliationError(f"National gates failed: {failed}")
        return ReconciliationResult(
            annual=reconciled_annual,
            monthly=reconciled_monthly,
            annual_adjustments=adjustments,
            monthly_factors=factors,
            monthly_differences=differences,
            seam_continuity=seam,
            gates=gates,
            review_flags=flags,
        )

    @staticmethod
    def _monthly_differences(
        before: pd.DataFrame, after: pd.DataFrame
    ) -> pd.DataFrame:
        differences = before[[PERIOD_COLUMN]].copy()
        for quantity in RECONCILED_QUANTITIES:
            differences[f"delta_{quantity}"] = (
                after[quantity] - before[quantity]
            )
            differences[f"pct_{quantity}"] = 100 * (
                after[quantity] / before[quantity] - 1
            )
        return differences

    def _seam_continuity(
        self,
        annual_before: pd.DataFrame,
        annual_after: pd.DataFrame,
        monthly_before: pd.DataFrame,
        monthly_after: pd.DataFrame,
    ) -> pd.DataFrame:
        last = self._policy.historical_end
        first = last + 1
        last_month, first_month = f"{last}-12", f"{first}-01"
        years_before = annual_before.set_index(YEAR_COLUMN)
        years_after = annual_after.set_index(YEAR_COLUMN)
        months_before = monthly_before.set_index(PERIOD_COLUMN)
        months_after = monthly_after.set_index(PERIOD_COLUMN)
        records = []
        for quantity in RECONCILED_QUANTITIES:
            annual_old = np.log(
                years_before.loc[first, quantity]
                / years_before.loc[last, quantity]
            )
            annual_new = np.log(
                years_after.loc[first, quantity]
                / years_after.loc[last, quantity]
            )
            monthly_old = np.log(
                months_before.loc[first_month, quantity]
                / months_before.loc[last_month, quantity]
            )
            monthly_new = np.log(
                months_after.loc[first_month, quantity]
                / months_after.loc[last_month, quantity]
            )
            records.append(
                {
                    "quantity": quantity,
                    "annual_change_before_log": float(annual_old),
                    "annual_change_after_log": float(annual_new),
                    "monthly_change_before_log": float(monthly_old),
                    "monthly_change_after_log": float(monthly_new),
                    "extra_annual_log": float(annual_new - annual_old),
                    "extra_monthly_log": float(monthly_new - monthly_old),
                }
            )
        return pd.DataFrame(records)

    def _evaluate(
        self,
        annual: pd.DataFrame,
        monthly: pd.DataFrame,
        adjustments: pd.DataFrame,
        differences: pd.DataFrame,
        seam: pd.DataFrame,
    ) -> tuple[dict[str, bool], dict[str, bool]]:
        policy = self._policy
        historical = annual[annual[YEAR_COLUMN] <= policy.historical_end]
        observed = adjustments[
            adjustments[YEAR_COLUMN] > policy.historical_end
        ]
        monthly_gap = max(
            (
                monthly["labor_force"]
                - monthly["employed"]
                - monthly["unemployed"]
            )
            .abs()
            .max(),
            (
                monthly["working_age"]
                - monthly["labor_force"]
                - monthly["inactive"]
            )
            .abs()
            .max(),
        )
        annual_gap = max(
            (
                historical["labor_force"]
                - historical["employed"]
                - historical["unemployed"]
            )
            .abs()
            .max(),
            (
                historical["working_age"]
                - historical["labor_force"]
                - historical["inactive"]
            )
            .abs()
            .max(),
        )
        max_bridge = float(
            seam[["extra_annual_log", "extra_monthly_log"]].abs().max().max()
        )
        gates = {
            "no_nonpositive": bool(
                (monthly[list(RECONCILED_QUANTITIES)] > 0).all().all()
            ),
            "identities_annual_exact": bool(annual_gap < 1e-6),
            "identities_monthly_exact": bool(monthly_gap < 1e-6),
            "observed_rounding_only": bool(
                observed["delta_persons"].abs().max()
                <= policy.max_observed_rounding_persons
            ),
            "working_age_below_population": bool(
                (monthly["working_age"] <= monthly["population"]).all()
            ),
            "no_new_large_bridge_shift": max_bridge
            <= policy.max_added_bridge_log_shift,
        }
        historical_changes = adjustments[
            adjustments[YEAR_COLUMN] <= policy.historical_end
        ]
        pct_columns = [f"pct_{q}" for q in RECONCILED_QUANTITIES]
        max_monthly = float(differences[pct_columns].abs().max().max()) / 100
        flags = {
            "annual_shift_review": float(
                historical_changes["relative_change"].abs().max()
            )
            > policy.max_annual_relative_shift,
            "monthly_shift_review": max_monthly
            > policy.max_monthly_relative_shift,
        }
        return gates, flags
