"""Minimum-curvature treatment of the reconstructed working age (ADR-006).

The national 1993-2000 working age is replaced by the curve closest to the
reconstruction with minimum curvature, subject to its eight annual means
and to the first observed months as fixed boundary conditions. The 33
departmental series are then smoothed jointly with the national monthly
total as a hard constraint. Inactive absorbs the change; employed,
unemployed and population are untouched, and nothing from 2001 changes.
The annual means are not collinear, so a single straight line cannot keep
them: this is minimum curvature, not an exact line.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import spsolve

from icml.reconciliation.solvers import MONTHS_PER_YEAR, second_difference

ORIGIN_LINEARIZED = "RECONSTRUIDO_PET_LINEALIZADA_1993_2000"
VERSION_LINEARIZED = "PET_MIN_CURVATURA_1993_2000"
VERSION_ORIGINAL = "PET_H4_ORIGINAL_INTACTA"
_ANCHOR_TOLERANCE = 1e-4
_NATIONAL_TOLERANCE = 1e-3
_CLOSURE_TOLERANCE = 1e-4
_IDENTITY_TOLERANCE = 1e-6
_POPULATION_TOLERANCE = 1e-5


class LinearizationError(ValueError):
    """Raised when the linearization would alter protected values."""


@dataclass(frozen=True)
class LinearizationPolicy:
    """Window, strengths and boundary of the linearization."""

    history_start: str
    history_end: str
    national_strength: float
    territorial_strength: float
    boundary_months: int

    def __post_init__(self) -> None:
        """Require positive strengths."""
        if min(self.national_strength, self.territorial_strength) <= 0:
            raise ValueError("Smoothing strengths must be positive")


def _history_length(periods: list[str], last: str) -> int:
    return sum(1 for p in periods if p <= last)


class WorkingAgeLinearizer:
    """Minimum-curvature working age, national then territorial."""

    def __init__(self, policy: LinearizationPolicy) -> None:
        """Store the policy."""
        self._policy = policy

    def national(
        self, national: pd.DataFrame
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Return the national series with linearized history.

        Raises
        ------
        LinearizationError
            If annual means are lost, values become non-positive or any
            month after the history changes.
        """
        policy = self._policy
        periods = list(national["period"])
        n_history = _history_length(periods, policy.history_end)
        working_age = np.array(
            national["employed"]
            + national["unemployed"]
            + national["inactive"],
            dtype=float,
        )
        years = np.array([int(p[:4]) for p in periods[:n_history]])
        anchored = sorted(set(years))
        rows, columns, weights, means = [], [], [], []
        for position, year in enumerate(anchored):
            months = np.flatnonzero(years == year)
            rows.extend([position] * MONTHS_PER_YEAR)
            columns.extend(months.tolist())
            weights.extend([1 / MONTHS_PER_YEAR] * MONTHS_PER_YEAR)
            means.append(working_age[months].mean())
        annual = sparse.csr_matrix(
            (weights, (rows, columns)), shape=(len(anchored), n_history)
        )
        means_array = np.asarray(means)
        boundary = policy.boundary_months
        curvature = second_difference(n_history + boundary)[:n_history, :]
        inner = curvature[:, :n_history]
        fixed_part = (
            curvature[:, n_history:]
            @ working_age[n_history : n_history + boundary]
        )
        quadratic = sparse.eye(
            n_history, format="csc"
        ) + policy.national_strength * (inner.T @ inner)
        scale = float(np.median(working_age[:n_history]))
        rhs = working_age[:n_history] / scale - policy.national_strength * (
            inner.T @ (fixed_part / scale)
        )
        kkt = sparse.bmat(
            [[quadratic, annual.T], [annual, None]], format="csc"
        )
        smooth = (
            spsolve(kkt, np.r_[rhs, means_array / scale])[:n_history] * scale
        )
        if (smooth <= 0).any():
            raise LinearizationError("Non-positive national working age")
        if np.max(np.abs(annual @ smooth - means_array)) > _ANCHOR_TOLERANCE:
            raise LinearizationError("Historical annual means not kept")
        result = national.copy(deep=True)
        history = result.index[:n_history]
        result.loc[history, "working_age"] = smooth
        result.loc[history, "inactive"] = (
            smooth
            - np.array(result.loc[history, "employed"])
            - np.array(result.loc[history, "unemployed"])
        )
        if (result.loc[history, "inactive"] <= 0).any():
            raise LinearizationError("Non-positive national inactive")
        result.loc[history, "origin"] = ORIGIN_LINEARIZED
        for column in national.columns:
            if not national.iloc[n_history:][column].equals(
                result.iloc[n_history:][column]
            ):
                raise LinearizationError(f"Observed month changed: {column}")
        before = np.diff(working_age[: n_history + boundary], 2)
        after = np.diff(
            np.r_[smooth, working_age[n_history : n_history + boundary]], 2
        )
        stats = {
            "max_working_age_change_pct": float(
                np.max(100 * np.abs(smooth / working_age[:n_history] - 1))
            ),
            "max_annual_mean_error_persons": float(
                np.max(np.abs(annual @ smooth - means_array))
            ),
            "curvature_energy_reduction_pct": float(
                100 * (1 - (after @ after) / (before @ before))
            ),
            "seam_change_before_pct": float(
                100 * (working_age[n_history] / working_age[n_history - 1] - 1)
            ),
            "seam_change_after_pct": float(
                100 * (working_age[n_history] / smooth[-1] - 1)
            ),
        }
        return result, stats

    def territorial(
        self, panel: pd.DataFrame, national: pd.DataFrame
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Smooth departmental working age under national monthly totals.

        Raises
        ------
        LinearizationError
            If national totals, identities, anchors or post-history
            values change.
        """
        policy = self._policy
        data = panel.sort_values(["dep_code", "period"]).reset_index(drop=True)
        codes = sorted(data["dep_code"].unique())
        periods = sorted(data["period"].unique())
        n_history = _history_length(periods, policy.history_end)
        boundary = policy.boundary_months
        reference = national.set_index("period").reindex(periods)
        baseline = np.stack(
            [
                np.array(
                    data.loc[data["dep_code"] == c, "working_age"], dtype=float
                )
                for c in codes
            ],
            axis=1,
        )
        target = np.array(reference["working_age"], dtype=float)[:n_history]
        scales = np.median(baseline[:n_history], axis=0)
        if (scales <= 0).any():
            raise LinearizationError("Non-positive working-age scales")
        national_scale = np.median(target)
        curvature = second_difference(n_history + boundary)[:n_history, :]
        inner, outer = curvature[:, :n_history], curvature[:, n_history:]
        block = (
            sparse.eye(n_history, format="csr")
            + policy.territorial_strength * inner.T @ inner
        ).tocsc()
        quadratic = sparse.block_diag([block] * len(codes), format="csc")
        normalized = (baseline[:n_history] / scales).T.reshape(-1)
        fixed = (outer @ baseline[n_history : n_history + boundary]).T
        rhs = normalized - policy.territorial_strength * np.concatenate(
            [inner.T @ (fixed[j] / scales[j]) for j in range(len(codes))]
        )
        rows = np.tile(np.arange(n_history), len(codes))
        columns = np.concatenate(
            [j * n_history + np.arange(n_history) for j in range(len(codes))]
        )
        weights = np.concatenate(
            [
                np.full(n_history, scales[j] / national_scale)
                for j in range(len(codes))
            ]
        )
        totals = sparse.csr_matrix(
            (weights, (rows, columns)),
            shape=(n_history, len(codes) * n_history),
        )
        kkt = sparse.bmat(
            [[quadratic, totals.T], [totals, None]], format="csc"
        )
        solution = spsolve(kkt, np.r_[rhs, target / national_scale])
        smooth = (
            solution[: len(codes) * n_history].reshape(len(codes), n_history).T
            * scales
        )
        if np.max(np.abs(smooth.sum(axis=1) - target)) > _NATIONAL_TOLERANCE:
            raise LinearizationError("Working age does not add to national")
        result = data.copy()
        in_history = result["period"] <= policy.history_end
        changes = []
        for j, code in enumerate(codes):
            rows_code = in_history & (result["dep_code"] == code)
            old_working_age = np.array(
                result.loc[rows_code, "working_age"], dtype=float
            )
            old_inactive = np.array(
                result.loc[rows_code, "inactive"], dtype=float
            )
            result.loc[rows_code, "working_age"] = smooth[:, j]
            result.loc[rows_code, "smoothed_working_age"] = smooth[:, j]
            result.loc[rows_code, "inactive"] = old_inactive + (
                smooth[:, j] - old_working_age
            )
            if (result.loc[rows_code, "inactive"] <= 0).any():
                raise LinearizationError(f"Negative inactive for {code}")
            result.loc[rows_code, "working_age_adjustment_persons"] = (
                result.loc[rows_code, "working_age"]
                - result.loc[rows_code, "working_age_pre_calibration"]
            )
            result.loc[rows_code, "working_age_adjustment_pct"] = 100 * (
                result.loc[rows_code, "working_age"]
                / result.loc[rows_code, "working_age_pre_calibration"]
                - 1
            )
            result.loc[rows_code, "working_age_population_rate_final"] = (
                result.loc[rows_code, "working_age"]
                / result.loc[rows_code, "labor_population_reconciled"]
            )
            result.loc[rows_code, "participation_rate_final"] = (
                result.loc[rows_code, "labor_force"]
                / result.loc[rows_code, "working_age"]
            )
            result.loc[rows_code, "employment_rate_final"] = (
                result.loc[rows_code, "employed"]
                / result.loc[rows_code, "working_age"]
            )
            changes.append(
                float(np.max(abs(smooth[:, j] / old_working_age - 1)) * 100)
            )
        result["working_age_version"] = np.where(
            in_history, VERSION_LINEARIZED, VERSION_ORIGINAL
        )
        self._verify(data, result, reference, periods, in_history)
        return result, {
            "max_departmental_change_pct": float(max(changes)),
            "mean_max_change_by_department_pct": float(np.mean(changes)),
        }

    @staticmethod
    def _verify(
        before: pd.DataFrame,
        after: pd.DataFrame,
        national: pd.DataFrame,
        periods: list[str],
        in_history: pd.Series,
    ) -> None:
        later_before = before[~in_history].reset_index(drop=True)
        later_after = after[~in_history].reset_index(drop=True)
        for column in before.columns:
            if not later_before[column].equals(later_after[column]):
                raise LinearizationError(f"Later month changed: {column}")
        if (
            after["working_age"]
            > after["labor_population_reconciled"] + _POPULATION_TOLERANCE
        ).any():
            raise LinearizationError("Working age above labor population")
        if not (after[["employed", "unemployed", "inactive"]] > 0).all().all():
            raise LinearizationError("Non-positive components")
        if (
            max(
                float(
                    abs(
                        after["working_age"]
                        - after["labor_force"]
                        - after["inactive"]
                    ).max()
                ),
                float(
                    abs(
                        after["labor_force"]
                        - after["employed"]
                        - after["unemployed"]
                    ).max()
                ),
            )
            > _IDENTITY_TOLERANCE
        ):
            raise LinearizationError("Identities broken")
        totals = (
            after.groupby("period")[
                [
                    "employed",
                    "unemployed",
                    "inactive",
                    "labor_force",
                    "working_age",
                    "labor_population_reconciled",
                ]
            ]
            .sum()
            .reindex(periods)
        )
        expected = {
            "employed": national["employed"],
            "unemployed": national["unemployed"],
            "inactive": national["inactive"],
            "labor_force": national["employed"] + national["unemployed"],
            "working_age": national["employed"]
            + national["unemployed"]
            + national["inactive"],
            "labor_population_reconciled": national["population"],
        }
        for column, values in expected.items():
            if (
                float(
                    np.max(np.abs(np.array(totals[column]) - np.array(values)))
                )
                > _CLOSURE_TOLERANCE
            ):
                raise LinearizationError(f"National not closed: {column}")
