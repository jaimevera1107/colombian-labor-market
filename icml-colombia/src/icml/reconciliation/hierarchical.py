"""Hierarchical closure: 33 departmental series add up to the national.

Steps, all reproducing RC1:

1. For the anchored departments, keep employed and unemployed, smooth
   working age and build a labor-domain population scaled to the official
   annual population.
2. Smooth working age jointly over the 33 territories under exact
   national monthly totals and the annual means of every anchored year.
3. Do the same for the labor-domain population.
4. Allocate the national residual of the three components among the
   unanchored territories with proportional fitting.
5. Regularize employed and unemployed jointly (national totals and annual
   anchors kept) and derive inactive as the remainder.

Official demographic projections are never overwritten; the reconciled
labor population is kept in its own column.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from icml.reconciliation.solvers import (
    SolverError,
    joint_smoother,
    proportional_fit,
    smooth_with_annual_means,
)

COMPONENTS: tuple[str, ...] = ("employed", "unemployed", "inactive")
LEVELS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
    "labor_population_reconciled",
)
PROVENANCE_ANCHORED = "ANCLA_ANUAL_23_PET_MENSUAL_SUAVIZADA"
PROVENANCE_RESIDUAL = "RESIDUO_NACIONAL_REPARTIDO_10"
_POPULATION_TOLERANCE = 1e-5
_IDENTITY_TOLERANCE = 1e-7
_RESIDUAL_ROW_TOLERANCE = 1e-3


class ClosureError(ValueError):
    """Raised when the hierarchical closure is infeasible or inexact."""


@dataclass(frozen=True)
class HierarchicalPolicy:
    """Smoothing strengths, fitting settings and tolerances."""

    working_age_strength: float
    population_strength: float
    employed_strength: float
    unemployed_strength: float
    ipf_max_iterations: int
    ipf_tolerance: float
    ipf_check_every: int
    ipf_floor: float
    national_tolerance_persons: float
    joint_tolerance_persons: float
    anchor_tolerance_persons: float
    rounded_anchor_tolerance_persons: float
    anchor_first_year: int
    anchor_last_year: int


@dataclass(frozen=True)
class ClosureResult:
    """Reconciled panel and audits."""

    panel: pd.DataFrame
    national_check: pd.DataFrame
    anchor_check: pd.DataFrame
    smoothness: pd.DataFrame
    summary: dict[str, Any]


class HierarchicalReconciler:
    """Close a 33-territory panel onto the national series."""

    def __init__(
        self, policy: HierarchicalPolicy, reconcile_population: bool = True
    ) -> None:
        """Store the policy.

        With ``reconcile_population=False`` (evaluation variant C), the
        labor population is not forced to the national total: anchored
        departments keep their anchor-matched population and unanchored
        ones their demographic projection.
        """
        self._policy = policy
        self._reconcile_population = reconcile_population

    def _fit(
        self, seed: np.ndarray, rows: np.ndarray, columns: np.ndarray
    ) -> np.ndarray:
        policy = self._policy
        return proportional_fit(
            seed,
            rows,
            columns,
            max_iterations=policy.ipf_max_iterations,
            tolerance=policy.ipf_tolerance,
            check_every=policy.ipf_check_every,
            floor=policy.ipf_floor,
        )

    def run(
        self,
        panel: pd.DataFrame,
        national: pd.DataFrame,
        anchors: pd.DataFrame,
    ) -> ClosureResult:
        """Reconcile ``panel`` (canonical columns) with ``national``.

        Raises
        ------
        ClosureError
            On coverage problems, infeasible residuals or inexact totals.
        """
        policy = self._policy
        data = panel.sort_values(["period", "dep_code"]).reset_index(drop=True)
        data["dep_code"] = data["dep_code"].astype(int)
        periods = sorted(data["period"].unique())
        codes = sorted(data["dep_code"].unique())
        fixed = sorted(anchors["dep_code"].unique())
        missing = sorted(set(codes) - set(fixed))
        if data.duplicated(subset=["period", "dep_code"]).any() or len(
            data
        ) != len(codes) * len(periods):
            raise ClosureError("Panel must be complete and unique")
        if sorted(national["period"]) != periods:
            raise ClosureError("National calendar differs from the panel")
        nat = national.set_index("period").reindex(periods).copy()
        nat["labor_force_canonical"] = nat["employed"] + nat["unemployed"]
        nat["working_age_canonical"] = (
            nat["labor_force_canonical"] + nat["inactive"]
        )
        years = np.array([int(p[:4]) for p in periods])
        original = data.set_index(["period", "dep_code"])

        def series(code: int, column: str) -> np.ndarray:
            return np.array(
                original.xs(code, level="dep_code").loc[periods, column],
                dtype=float,
            )

        output = data.copy()
        output["working_age_pre_calibration"] = output["working_age"]
        output["demographic_population_original"] = output[
            "population_demographic_projection"
        ]
        output["labor_population_reconciled"] = np.nan
        output["smoothed_working_age"] = np.nan
        output = output.set_index(["period", "dep_code"])

        def put(code: int, column: str, values: np.ndarray) -> None:
            output.loc[(periods, code), column] = values

        for code in fixed:
            annual = anchors[anchors["dep_code"] == code]
            working_age = series(code, "working_age")
            targets = {
                int(y): float(working_age[years == y].mean())
                for y in annual["year"]
            }
            smoothed = smooth_with_annual_means(
                working_age, years, targets, policy.working_age_strength
            )
            employed = series(code, "employed")
            unemployed = series(code, "unemployed")
            inactive = smoothed - employed - unemployed
            if (inactive < 0).any():
                raise ClosureError(f"Negative inactive for {code}")
            put(code, "working_age", smoothed)
            put(code, "labor_force", employed + unemployed)
            put(code, "inactive", inactive)
            put(code, "smoothed_working_age", smoothed)
            demographic = series(code, "population_demographic_projection")
            factors = [
                (
                    int(r.year),
                    float(r.population)
                    / float(demographic[years == int(r.year)].mean()),
                )
                for r in annual.itertuples()
            ]
            factor_years = np.array([f[0] for f in factors])
            factor_values = np.array([f[1] for f in factors])
            monthly_factor = np.interp(
                years,
                factor_years,
                factor_values,
                left=factor_values[0],
                right=factor_values[-1],
            )
            population = smooth_with_annual_means(
                demographic * monthly_factor,
                years,
                dict(
                    zip(
                        annual["year"].astype(int),
                        annual["population"],
                        strict=True,
                    )
                ),
                policy.population_strength,
            )
            if (population + _POPULATION_TOLERANCE < smoothed).any():
                raise ClosureError(f"Working age above population: {code}")
            put(code, "labor_population_reconciled", population)

        working_age_all = np.stack(
            [series(c, "working_age") for c in codes], axis=1
        )
        component_sum = [
            float(r.employed) + float(r.unemployed) + float(r.inactive)
            for r in anchors.itertuples()
        ]
        joint_working_age = joint_smoother(
            working_age_all,
            codes,
            years,
            np.array(nat["working_age_canonical"], dtype=float),
            anchors,
            policy.working_age_strength,
            component_sum,
            policy.joint_tolerance_persons,
        )
        position = {c: j for j, c in enumerate(codes)}
        for code in fixed:
            values = joint_working_age[:, position[code]]
            inactive = (
                values - series(code, "employed") - series(code, "unemployed")
            )
            if (inactive <= 0).any():
                raise ClosureError(f"Joint working age: inactive <= 0 {code}")
            put(code, "working_age", values)
            put(code, "inactive", inactive)
            put(code, "smoothed_working_age", values)

        baselines = [
            np.array(
                output.loc[(periods, c), "labor_population_reconciled"],
                dtype=float,
            )
            if c in fixed
            else series(c, "population_demographic_projection")
            for c in codes
        ]
        if self._reconcile_population:
            joint_population = joint_smoother(
                np.stack(baselines, axis=1),
                codes,
                years,
                np.array(nat["population"], dtype=float),
                anchors,
                policy.population_strength,
                list(anchors["population"]),
                policy.joint_tolerance_persons,
            )
            for code in fixed:
                put(
                    code,
                    "labor_population_reconciled",
                    joint_population[:, position[code]],
                )
        else:
            joint_population = np.stack(baselines, axis=1)

        self._allocate_residual(
            output,
            original,
            periods,
            fixed,
            missing,
            position,
            nat,
            joint_working_age,
            joint_population,
        )
        for column, source, strength in (
            ("employed", "employed", policy.employed_strength),
            ("unemployed", "unemployed", policy.unemployed_strength),
        ):
            baseline = np.stack(
                [
                    np.array(output.loc[(periods, c), column], dtype=float)
                    for c in codes
                ],
                axis=1,
            )
            smoothed = joint_smoother(
                baseline,
                codes,
                years,
                np.array(nat[source], dtype=float),
                anchors,
                strength,
                list(anchors[source]),
                policy.joint_tolerance_persons,
            )
            if (smoothed <= 0).any():
                raise ClosureError(f"Regularized {column} not positive")
            for code in codes:
                put(code, column, smoothed[:, position[code]])
        for code in codes:
            subset = output.loc[(periods, code), :]
            remaining = (
                np.array(subset["working_age"])
                - np.array(subset["employed"])
                - np.array(subset["unemployed"])
            )
            if (remaining <= 0).any():
                raise ClosureError(f"Negative inactive in {code}")
            put(code, "inactive", remaining)
        result = self._finalize(output, data, fixed)
        return self._audit(result, data, nat, anchors, fixed, missing, periods)

    def _allocate_residual(
        self,
        output: pd.DataFrame,
        original: pd.DataFrame,
        periods: list[str],
        fixed: Sequence[int],
        missing: Sequence[int],
        position: dict[int, int],
        nat: pd.DataFrame,
        joint_working_age: np.ndarray,
        joint_population: np.ndarray,
    ) -> None:
        anchored = output[
            output.index.get_level_values("dep_code").isin(fixed)
        ].groupby(level="period")
        fixed_sum = (
            anchored[
                [
                    "employed",
                    "unemployed",
                    "inactive",
                    "working_age",
                    "labor_population_reconciled",
                ]
            ]
            .sum()
            .reindex(periods)
        )
        residual = np.stack(
            [np.array(nat[c], dtype=float) for c in COMPONENTS], axis=1
        ) - np.array(fixed_sum[list(COMPONENTS)], dtype=float)
        residual_working_age = np.array(
            nat["working_age_canonical"]
        ) - np.array(fixed_sum["working_age"])
        residual_population = np.array(nat["population"]) - np.array(
            fixed_sum["labor_population_reconciled"]
        )
        population_infeasible = self._reconcile_population and bool(
            (residual_population - residual_working_age <= 0).any()
        )
        if (
            (residual <= 0).any()
            or (residual_working_age <= 0).any()
            or population_infeasible
        ):
            raise ClosureError("Infeasible closure with anchored territories")
        predicted = np.stack(
            [
                np.array(
                    original.xs(c, level="dep_code").loc[
                        periods, list(COMPONENTS)
                    ],
                    dtype=float,
                )
                for c in missing
            ],
            axis=1,
        )
        columns = [position[c] for c in missing]
        allocated = np.empty((len(periods), len(missing), 3))
        working_age_target = np.empty((len(periods), len(missing)))
        population_target = np.empty((len(periods), len(missing)))
        for month, period in enumerate(periods):
            row = joint_working_age[month, columns].copy()
            if (
                abs(row.sum() - residual_working_age[month])
                >= _RESIDUAL_ROW_TOLERANCE
            ):
                raise ClosureError(f"Residual mismatch in {period}")
            row *= residual_working_age[month] / row.sum()
            if (row <= 0).any():
                raise ClosureError("Negative allocated working age")
            allocated[month] = self._fit(
                predicted[month], row, residual[month]
            )
            working_age_target[month] = row
            population_target[month] = joint_population[month, columns]
            if self._reconcile_population:
                population_target[month] *= (
                    residual_population[month] / population_target[month].sum()
                )
            if (population_target[month] < row).any():
                raise ClosureError(f"Population below working age: {period}")
        for j, code in enumerate(missing):
            output.loc[(periods, code), "employed"] = allocated[:, j, 0]
            output.loc[(periods, code), "unemployed"] = allocated[:, j, 1]
            output.loc[(periods, code), "inactive"] = allocated[:, j, 2]
            output.loc[(periods, code), "labor_force"] = (
                allocated[:, j, 0] + allocated[:, j, 1]
            )
            output.loc[(periods, code), "working_age"] = working_age_target[
                :, j
            ]
            output.loc[(periods, code), "smoothed_working_age"] = (
                working_age_target[:, j]
            )
            output.loc[(periods, code), "labor_population_reconciled"] = (
                population_target[:, j]
            )

    @staticmethod
    def _finalize(
        output: pd.DataFrame, data: pd.DataFrame, fixed: Sequence[int]
    ) -> pd.DataFrame:
        result = (
            output.reset_index()
            .sort_values(["dep_code", "period"])
            .reset_index(drop=True)
        )
        for column in LEVELS:
            if result[column].isna().any():
                raise ClosureError(f"Missing values in {column}")
        result["panel_population_original"] = result[
            "population_demographic_projection"
        ]
        result["working_age_adjustment_persons"] = (
            result["working_age"] - result["working_age_pre_calibration"]
        )
        result["working_age_adjustment_pct"] = 100 * (
            result["working_age"] / result["working_age_pre_calibration"] - 1
        )
        result["labor_population_adjustment_pct"] = 100 * (
            result["labor_population_reconciled"]
            / result["demographic_population_original"]
            - 1
        )
        result["labor_force"] = result["employed"] + result["unemployed"]
        result["working_age"] = result["labor_force"] + result["inactive"]
        result["employment_rate_final"] = (
            result["employed"] / result["working_age"]
        )
        result["unemployment_rate_final"] = (
            result["unemployed"] / result["labor_force"]
        )
        result["participation_rate_final"] = (
            result["labor_force"] / result["working_age"]
        )
        result["working_age_population_rate_final"] = (
            result["working_age"] / result["labor_population_reconciled"]
        )
        result["hierarchical_provenance"] = np.where(
            result["dep_code"].isin(list(fixed)),
            PROVENANCE_ANCHORED,
            PROVENANCE_RESIDUAL,
        )
        return result

    def _audit(
        self,
        result: pd.DataFrame,
        original: pd.DataFrame,
        nat: pd.DataFrame,
        anchors: pd.DataFrame,
        fixed: Sequence[int],
        missing: Sequence[int],
        periods: list[str],
    ) -> ClosureResult:
        policy = self._policy
        totals = result.groupby("period")[list(LEVELS)].sum().reindex(periods)
        targets = {
            "employed": "employed",
            "unemployed": "unemployed",
            "inactive": "inactive",
            "labor_force": "labor_force_canonical",
            "working_age": "working_age_canonical",
            "labor_population_reconciled": "population",
        }
        check = pd.DataFrame({"period": periods})
        for column, source in targets.items():
            check[f"national_{column}"] = np.array(nat[source])
            check[f"departments_{column}"] = np.array(totals[column])
            check[f"residual_{column}"] = (
                check[f"departments_{column}"] - check[f"national_{column}"]
            )
            enforced = self._reconcile_population or (
                column != "labor_population_reconciled"
            )
            if (
                enforced
                and check[f"residual_{column}"].abs().max()
                >= policy.national_tolerance_persons
            ):
                raise ClosureError(f"National total not closed: {column}")
        if (
            max(
                float(
                    (
                        result["labor_force"]
                        - result["employed"]
                        - result["unemployed"]
                    )
                    .abs()
                    .max()
                ),
                float(
                    (
                        result["working_age"]
                        - result["labor_force"]
                        - result["inactive"]
                    )
                    .abs()
                    .max()
                ),
            )
            >= _IDENTITY_TOLERANCE
        ):
            raise ClosureError("Identities not closed")
        if (result[list(COMPONENTS)] < 0).any().any() or (
            result["labor_population_reconciled"] + _POPULATION_TOLERANCE
            < result["working_age"]
        ).any():
            raise ClosureError("Inadmissible reconciled levels")
        window = result[
            result["dep_code"].isin(list(fixed))
            & result["year"].between(
                policy.anchor_first_year, policy.anchor_last_year
            )
        ]
        got = window.groupby(["dep_code", "year"])[list(LEVELS)].mean()
        annual = got.join(
            anchors.set_index(["dep_code", "year"])[
                [
                    "employed",
                    "unemployed",
                    "inactive",
                    "labor_force",
                    "working_age",
                    "population",
                ]
            ],
            rsuffix="_source",
        )
        sources = {
            "employed": "employed_source",
            "unemployed": "unemployed_source",
            "inactive": "inactive_source",
            "labor_force": "labor_force_source",
            "working_age": "working_age_source",
            "labor_population_reconciled": "population",
        }
        for column, source in sources.items():
            annual[f"error_{column}"] = annual[column] - annual[source]
            ceiling = (
                policy.rounded_anchor_tolerance_persons
                if column in ("labor_force", "working_age")
                else policy.anchor_tolerance_persons
            )
            if annual[f"error_{column}"].abs().max() > ceiling:
                raise ClosureError(f"Annual anchor not kept: {column}")
        smoothness = self._smoothness(result, original)
        summary = {
            "territories": len(fixed) + len(missing),
            "anchored": len(fixed),
            "residual_units": len(missing),
            "max_national_residual_persons": {
                c: float(check[f"residual_{c}"].abs().max()) for c in targets
            },
            "max_anchor_error_persons": {
                c: float(annual[f"error_{c}"].abs().max()) for c in sources
            },
            "max_working_age_adjustment_pct": float(
                result["working_age_adjustment_pct"].abs().max()
            ),
            "max_labor_population_vs_demographic_pct": float(
                result["labor_population_adjustment_pct"].abs().max()
            ),
        }
        return ClosureResult(
            panel=result,
            national_check=check,
            anchor_check=annual.reset_index(),
            smoothness=smoothness,
            summary=summary,
        )

    @staticmethod
    def _smoothness(
        result: pd.DataFrame, original: pd.DataFrame
    ) -> pd.DataFrame:
        rows = []
        for code, frame in result.groupby("dep_code"):
            frame = frame.sort_values("period")
            before = original[original["dep_code"] == code].sort_values(
                "period"
            )
            for name, after_values, before_values in (
                (
                    "PET",
                    np.array(frame["working_age"]),
                    np.array(before["working_age"]),
                ),
                (
                    "POBLACION_LABORAL",
                    np.array(frame["labor_population_reconciled"]),
                    np.array(
                        before["population_demographic_projection"],
                        dtype=float,
                    ),
                ),
            ):
                second = np.diff(after_values, 2)
                scale = float(np.median(after_values))
                abrupt = 100 * np.abs(second) / scale
                rows.append(
                    {
                        "dep_code": int(code),
                        "quantity": name,
                        "max_curvature_pct": float(abrupt.max()),
                        "p99_curvature_pct": float(np.quantile(abrupt, 0.99)),
                        "max_curvature_before_pct": float(
                            100
                            * np.abs(np.diff(before_values, 2)).max()
                            / np.median(before_values)
                        ),
                        "months_curvature_above_2_pct": int(
                            (abrupt > 2).sum()
                        ),
                        "max_monthly_jump_pct": float(
                            100 * np.max(np.abs(np.diff(after_values))) / scale
                        ),
                        "median_monthly_change_pct": float(
                            np.median(np.abs(np.diff(after_values)))
                            / scale
                            * 100
                        ),
                        "max_adjustment_vs_pre_pct": float(
                            100
                            * np.max(np.abs(after_values / before_values - 1))
                        ),
                        "max_curvature_period": str(
                            frame["period"].iloc[
                                int(np.argmax(np.abs(second))) + 1
                            ]
                        ),
                    }
                )
        return pd.DataFrame(rows)


__all__ = [
    "ClosureError",
    "HierarchicalPolicy",
    "HierarchicalReconciler",
    "SolverError",
]
