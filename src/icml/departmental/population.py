"""Demographic backcast of departmental population (B1 revision).

Before the first anchored year the reconstruction inherits the national
population dynamics, which can diverge strongly from each territory's own
demography. The revision replaces only the pre-anchor population with the
department's demographic projection, rescaled to its official GEIH level
in the calibration year, interpolated monthly with a monotone PCHIP curve
and rebalanced to reproduce every annual target exactly. All other series
and all anchored years are untouched.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

from icml.departmental.anchors import QUANTITIES

_MONTH_CENTER = 0.5
_MONTHS_PER_YEAR = 12
_LABOR_SERIES = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
)
_IDENTITY_TOLERANCE = 1e-5


class PopulationRevisionError(ValueError):
    """Raised when the population revision breaks its contract."""


@dataclass(frozen=True)
class PopulationPolicy:
    """Calendar, validation folds and tolerances of the revision."""

    calibration_year: int
    backcast_start_year: int
    backcast_end_year: int
    holdout_calibration_start: int
    holdout_calibration_end: int
    holdout_evaluation_start: int
    holdout_evaluation_end: int
    anchor_tolerance_persons: float
    demographic_tolerance_persons: float
    link_quantiles: Sequence[float]
    large_link_change: float

    @property
    def backcast_years(self) -> list[int]:
        """Return the years whose population is revised."""
        return list(
            range(self.backcast_start_year, self.backcast_end_year + 1)
        )


@dataclass(frozen=True)
class PopulationRevisionResult:
    """Revised panel and its audit tables."""

    panel: pd.DataFrame
    calibration: pd.DataFrame
    backtest: pd.DataFrame
    link_audit: pd.DataFrame
    quality: dict[str, Any]


class DemographicPopulationBackcast:
    """Replace pre-anchor population with rescaled demographic trends."""

    def __init__(self, policy: PopulationPolicy) -> None:
        """Store the policy."""
        self._policy = policy

    def revise(
        self,
        panel: pd.DataFrame,
        projections: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return the revised panel and the per-department calibration."""
        policy = self._policy
        years = policy.backcast_years
        projection_years = np.arange(
            policy.backcast_start_year, policy.calibration_year + 1
        )
        months = pd.period_range(f"{years[0]}-01", f"{years[-1]}-12", freq="M")
        position = (
            months.year + (months.month - _MONTH_CENTER) / _MONTHS_PER_YEAR
        )
        revised = panel.copy()
        rows = []
        for code, group in panel.groupby("dep_code", sort=True):
            projection = projections.loc[
                (projections["dep_code"] == code)
                & projections["year"].between(
                    projection_years[0], projection_years[-1]
                )
            ].sort_values("year")
            if not np.array_equal(
                np.array(projection["year"]), projection_years
            ):
                raise PopulationRevisionError(
                    f"Projection years incomplete for {code}"
                )
            official = float(
                anchors.loc[
                    (anchors["dep_code"] == code)
                    & (anchors["year"] == policy.calibration_year),
                    "population",
                ].iloc[0]
            )
            projected = float(
                projection.loc[
                    projection["year"] == policy.calibration_year,
                    "population_demographic_projection",
                ].iloc[0]
            )
            factor = official / projected
            targets = (
                np.array(
                    projection["population_demographic_projection"],
                    dtype=float,
                )
                * factor
            )
            monthly = PchipInterpolator(
                np.array(projection["year"], dtype=float) + _MONTH_CENTER,
                targets,
            )(position)
            for offset, year in enumerate(years):
                mask = months.year == year
                monthly[mask] *= targets[offset] / monthly[mask].mean()
            index = revised.index[
                (revised["dep_code"] == code)
                & (revised["year"] < policy.calibration_year)
            ]
            if revised.loc[index, "period"].tolist() != list(
                months.astype(str)
            ):
                raise PopulationRevisionError(
                    f"Backcast months misaligned for {code}"
                )
            revised.loc[index, "population"] = monthly
            first = f"{policy.calibration_year}-01"
            last = f"{policy.calibration_year - 1}-12"
            january = float(
                group.loc[group["period"] == first, "population"].iloc[0]
            )
            december_old = float(
                group.loc[group["period"] == last, "population"].iloc[0]
            )
            rows.append(
                {
                    "dep_code": int(code),
                    "department": str(group["department"].iloc[0]),
                    "scale_factor": float(factor),
                    "max_annual_target_error_persons": float(
                        max(
                            abs(
                                monthly[months.year == year].mean()
                                - targets[k]
                            )
                            for k, year in enumerate(years)
                        )
                    ),
                    "seam_change_pct_new": 100 * (january / monthly[-1] - 1),
                    "seam_change_pct_old": 100 * (january / december_old - 1),
                }
            )
        return revised, pd.DataFrame(rows)

    def backtest(
        self,
        anchors: pd.DataFrame,
        projections: pd.DataFrame,
        national: pd.DataFrame,
    ) -> pd.DataFrame:
        """Hide early anchored years and compare two population signals.

        Calibrates a level factor on later years and evaluates on earlier
        ones, using either the national population or the department's
        demographic projection as the signal.
        """
        policy = self._policy
        reference = national.copy()
        reference["year"] = reference["period"].str.slice(0, 4).astype(int)
        national_years = reference[
            reference["year"].between(
                policy.holdout_evaluation_start, policy.holdout_calibration_end
            )
        ]
        national_annual = (
            national_years.groupby("year")["population"]
            .mean()
            .rename("national")
            .reset_index()
        )
        source = anchors.merge(
            projections[
                ["dep_code", "year", "population_demographic_projection"]
            ],
            on=["dep_code", "year"],
            validate="one_to_one",
        ).merge(national_annual, on="year", validate="many_to_one")
        rows = []
        for code, group in source.groupby("dep_code"):
            train = group[
                group["year"].between(
                    policy.holdout_calibration_start,
                    policy.holdout_calibration_end,
                )
            ]
            test = group[
                group["year"].between(
                    policy.holdout_evaluation_start,
                    policy.holdout_evaluation_end,
                )
            ]
            for method, column in (
                ("national", "national"),
                (
                    "departmental_projection",
                    "population_demographic_projection",
                ),
            ):
                factor = train["population"].sum() / train[column].sum()
                predicted = test[column] * factor
                rows.append(
                    {
                        "dep_code": int(code),
                        "department": str(group["department"].iloc[0]),
                        "method": method,
                        "holdout_wape_pct": float(
                            100
                            * np.abs(predicted - test["population"]).sum()
                            / test["population"].sum()
                        ),
                        "calibration_factor": float(factor),
                    }
                )
        return pd.DataFrame(rows)

    def link_audit(
        self, panel: pd.DataFrame, national: pd.DataFrame
    ) -> pd.DataFrame:
        """Compare the first anchored month-on-month change with history."""
        policy = self._policy
        first = f"{policy.calibration_year}-01"
        last = f"{policy.calibration_year - 1}-12"
        reference = national.set_index("period")
        ordered = panel.sort_values(["dep_code", "period"])
        low_q, high_q = policy.link_quantiles
        rows = []
        for quantity in ("employed", "unemployed", "inactive", "population"):
            national_change = float(
                np.log(
                    reference.loc[first, quantity]
                    / reference.loc[last, quantity]
                )
            )
            anchored = ordered[ordered["year"] >= policy.calibration_year]
            changes = (
                anchored.groupby("dep_code")[quantity]
                .transform(lambda x: np.log(x).diff().abs())
                .dropna()
            )
            low, high = (
                float(changes.quantile(low_q)),
                float(changes.quantile(high_q)),
            )
            for code, group in ordered.groupby("dep_code"):
                before = float(
                    group.loc[group["period"] == last, quantity].iloc[0]
                )
                after = float(
                    group.loc[group["period"] == first, quantity].iloc[0]
                )
                change = float(np.log(after / before))
                rows.append(
                    {
                        "dep_code": int(code),
                        "department": str(group["department"].iloc[0]),
                        "quantity": quantity,
                        "link_log_change_pct": 100 * change,
                        "national_log_change_pct": 100 * national_change,
                        "residual_to_national_pct_log": 100
                        * (change - national_change),
                        "empirical_low_abs_log_pct": 100 * low,
                        "empirical_high_abs_log_pct": 100 * high,
                        "above_high_quantile": abs(change) > high,
                        "above_large_change": abs(after / before - 1)
                        > policy.large_link_change,
                    }
                )
        return pd.DataFrame(rows)

    def verify(
        self,
        original: pd.DataFrame,
        revised: pd.DataFrame,
        anchors: pd.DataFrame,
        projections: pd.DataFrame,
        calibration: pd.DataFrame,
    ) -> dict[str, Any]:
        """Check immutability, identities and both kinds of anchors.

        Raises
        ------
        PopulationRevisionError
            If any invariant fails.
        """
        policy = self._policy
        keys = ["dep_code", "period"]
        before = original.sort_values(keys).reset_index(drop=True)
        after = revised.sort_values(keys).reset_index(drop=True)
        if not before[keys].equals(after[keys]):
            raise PopulationRevisionError("Panel keys changed")
        for series in _LABOR_SERIES:
            if not np.array_equal(
                np.array(before[series]), np.array(after[series])
            ):
                raise PopulationRevisionError(f"{series} was modified")
        anchored = before["year"] >= policy.calibration_year
        if not np.array_equal(
            np.array(before.loc[anchored, "population"]),
            np.array(after.loc[anchored, "population"]),
        ):
            raise PopulationRevisionError("Anchored population modified")
        values = after[list(QUANTITIES)]
        if (
            (values <= 0).any().any()
            or values.isna().any().any()
            or (after["working_age"] > after["population"]).any()
        ):
            raise PopulationRevisionError("Inadmissible revised values")
        residual = max(
            float(
                (
                    after["labor_force"]
                    - after["employed"]
                    - after["unemployed"]
                )
                .abs()
                .max()
            ),
            float(
                (
                    after["working_age"]
                    - after["labor_force"]
                    - after["inactive"]
                )
                .abs()
                .max()
            ),
        )
        if residual >= _IDENTITY_TOLERANCE:
            raise PopulationRevisionError("Identities not closed")
        anchor_gap = 0.0
        for quantity in QUANTITIES:
            means = (
                after.loc[anchored]
                .groupby(["dep_code", "year"])[quantity]
                .mean()
                .reset_index()
            )
            merged = means.merge(
                anchors[["dep_code", "year", quantity]],
                on=["dep_code", "year"],
                suffixes=("_month", "_annual"),
            )
            anchor_gap = max(
                anchor_gap,
                float(
                    (
                        merged[f"{quantity}_month"]
                        - merged[f"{quantity}_annual"]
                    )
                    .abs()
                    .max()
                ),
            )
        if anchor_gap >= policy.anchor_tolerance_persons:
            raise PopulationRevisionError("Annual GEIH anchors not kept")
        early = (
            after.loc[~anchored]
            .groupby(["dep_code", "year"])["population"]
            .mean()
            .reset_index()
            .merge(
                projections[
                    ["dep_code", "year", "population_demographic_projection"]
                ],
                on=["dep_code", "year"],
            )
            .merge(calibration[["dep_code", "scale_factor"]], on="dep_code")
        )
        demographic_gap = float(
            (
                early["population"]
                - early["population_demographic_projection"]
                * early["scale_factor"]
            )
            .abs()
            .max()
        )
        if demographic_gap > policy.demographic_tolerance_persons:
            raise PopulationRevisionError("Scaled projection not kept")
        return {
            "max_identity_residual_persons": residual,
            "max_annual_geih_error_persons": anchor_gap,
            "max_demographic_target_error_persons": demographic_gap,
        }

    def run(
        self,
        panel: pd.DataFrame,
        projections: pd.DataFrame,
        anchors: pd.DataFrame,
        national: pd.DataFrame,
    ) -> PopulationRevisionResult:
        """Revise, audit and verify."""
        revised, calibration = self.revise(panel, projections, anchors)
        quality = self.verify(
            panel, revised, anchors, projections, calibration
        )
        return PopulationRevisionResult(
            panel=revised,
            calibration=calibration,
            backtest=self.backtest(anchors, projections, national),
            link_audit=self.link_audit(revised, national),
            quality=quality,
        )
