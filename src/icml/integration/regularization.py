"""Control of implausible month-to-month jumps in latent urban unemployment.

Latent months reproduce the windows exactly but can oscillate strongly for
small cities. Two scenarios are built, both limited to unemployment in the
latent segment:

* **strict**: the 57 windows stay exact; the smallest bidirectional growth
  cap compatible with them (at least the policy cap) bounds the month-to-
  month ratio;
* **quality filter**: strict for regularized cities, unchanged where no
  jump exceeds the cap, and, for listed small cities where the cap is not
  attainable with exact windows, a bounded window tolerance with the
  smallest attainable cap. The tolerance is a modeling assumption, not a
  DANE sampling margin.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import (
    Bounds,
    LinearConstraint,
    OptimizeResult,
    linprog,
    minimize,
)

from icml.integration.recent import with_urban_rates
from icml.integration.windows import (
    WINDOW_LENGTH,
    rolling_design,
    window_prior,
)

TARGET = "unemployed"
FIELDS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "population",
    "labor_force",
    "working_age",
)
RULE_UNCHANGED = "unchanged"
RULE_STRICT = "strict_exact_windows"
RULE_FLEXIBLE = "flexible_bounded_tolerance"
RULE_SYNTHETIC = "synthetic_unchanged"
_GROWTH_TOLERANCE = 1e-4
_WINDOW_TOLERANCE = 1e-6
_FLOOR_TOLERANCE = 1e-5
_RATIO_EPSILON = 1e-9
_CAP_SEARCH_LIMIT = 128.0
_IDENTITY_TOLERANCE = 1e-5


class RegularizationError(ValueError):
    """Raised when a regularized series violates its constraints."""


@dataclass(frozen=True)
class RegularizationPolicy:
    """Caps, floors, objective weights and search settings."""

    max_monthly_ratio: float
    relative_floor: float
    tolerance_margin: float
    strict_cap_buffer: float
    cap_bisection_steps: int
    flexible_codes: Sequence[int]
    max_flexible_window_tolerance: float
    flexible_cap_buffer: float
    flexible_cap_lower: float
    flexible_bisection_steps: int
    prior_weight: float
    incumbent_weight: float
    first_difference_weight: float
    second_difference_weight: float
    exact_solver_tolerance: float
    exact_solver_max_iterations: int
    soft_solver_tolerance: float
    soft_solver_max_iterations: int


def window_matrix(n_windows: int) -> np.ndarray:
    """Return the ``n_windows x n_months`` rolling-mean operator."""
    n_months = n_windows + WINDOW_LENGTH - 1
    matrix = np.zeros((n_windows, n_months))
    for window in range(n_windows):
        matrix[window, window : window + WINDOW_LENGTH] = 1 / WINDOW_LENGTH
    return matrix


def growth_matrix(n_months: int, cap: float) -> np.ndarray:
    """Rows encoding ``x_t <= cap x_(t-1)`` and ``x_(t-1) <= cap x_t``."""
    matrix = np.zeros((2 * (n_months - 1), n_months))
    for month in range(1, n_months):
        matrix[2 * (month - 1), month] = 1
        matrix[2 * (month - 1), month - 1] = -cap
        matrix[2 * (month - 1) + 1, month - 1] = 1
        matrix[2 * (month - 1) + 1, month] = -cap
    return matrix


def jump_metrics(values: np.ndarray, cap: float) -> dict[str, float]:
    """Summarize month-to-month ratios of a positive series."""
    ratios = values[1:] / values[:-1]
    return {
        "max_increase_pct": float(100 * (max(ratios) - 1)),
        "max_decrease_pct": float(100 * (1 - min(ratios))),
        "months_increase_above_cap": int(
            np.sum(ratios > cap + _RATIO_EPSILON)
        ),
        "bidirectional_above_cap": int(
            np.sum(np.maximum(ratios, 1 / ratios) > cap + _RATIO_EPSILON)
        ),
        "p99_abs_log_change": float(np.percentile(np.abs(np.log(ratios)), 99)),
        "minimum": float(np.min(values)),
    }


class JumpRegularizer:
    """Constrained quadratic programs on the latent monthly series."""

    def __init__(self, policy: RegularizationPolicy) -> None:
        """Store the policy."""
        self._policy = policy

    def _scaled(
        self, windows: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, np.ndarray]:
        design, offset, lower = rolling_design(
            windows, self._policy.relative_floor
        )
        return (
            design,
            offset,
            lower,
            float(np.mean(windows)),
            window_matrix(len(windows)),
        )

    def min_window_tolerance(self, windows: np.ndarray, cap: float) -> float:
        """Smallest uniform relative window deviation allowing ``cap``.

        Raises
        ------
        RegularizationError
            If the linear program is infeasible.
        """
        _, _, _, scale, rolling = self._scaled(windows)
        normalized = windows / scale
        n_months = rolling.shape[1]
        growth = growth_matrix(n_months, cap)
        n_windows = len(windows)
        system = np.zeros((2 * n_windows + growth.shape[0], n_months + 1))
        system[:n_windows, :n_months] = rolling
        system[:n_windows, n_months] = -normalized
        system[n_windows : 2 * n_windows, :n_months] = -rolling
        system[n_windows : 2 * n_windows, n_months] = -normalized
        system[2 * n_windows :, :n_months] = growth
        bound = np.r_[normalized, -normalized, np.zeros(len(growth))]
        floor = self._policy.relative_floor * float(np.min(normalized))
        cost = np.zeros(n_months + 1)
        cost[-1] = 1
        result = linprog(
            cost,
            A_ub=system,
            b_ub=bound,
            bounds=[(floor, None)] * n_months + [(0, None)],
            method="highs",
        )
        if not result.success:
            raise RegularizationError(
                f"Minimum tolerance LP infeasible: {result.message}"
            )
        return float(max(0.0, result.x[-1]))

    def _exact_feasibility(
        self, windows: np.ndarray, cap: float
    ) -> OptimizeResult:
        design, offset, lower, scale, _ = self._scaled(windows)
        growth = growth_matrix(design.shape[0], cap)
        return linprog(
            np.zeros(WINDOW_LENGTH),
            A_ub=growth @ design,
            b_ub=-(growth @ (offset / scale)),
            A_eq=np.ones((1, WINDOW_LENGTH)),
            b_eq=[WINDOW_LENGTH * windows[0] / scale],
            bounds=[(float(v / scale), None) for v in lower],
            method="highs",
        )

    def min_exact_cap(self, windows: np.ndarray) -> float:
        """Smallest bidirectional cap compatible with exact windows.

        Raises
        ------
        RegularizationError
            If no cap up to the search limit is feasible.
        """
        lower = self._policy.max_monthly_ratio
        if self._exact_feasibility(windows, lower).success:
            return float(lower)
        low, high = float(lower), 2 * float(lower)
        while not self._exact_feasibility(windows, high).success:
            high *= 2
            if high > _CAP_SEARCH_LIMIT:
                raise RegularizationError("No feasible cap with exact windows")
        for _ in range(self._policy.cap_bisection_steps):
            middle = (low + high) / 2
            if self._exact_feasibility(windows, middle).success:
                high = middle
            else:
                low = middle
        return high

    def _objective(
        self, prior: np.ndarray, incumbent: np.ndarray, scale: float
    ) -> tuple[np.ndarray, np.ndarray]:
        policy = self._policy
        prior, incumbent = prior / scale, incumbent / scale
        n_months = len(prior)
        first = np.diff(np.eye(n_months), axis=0)
        second = np.diff(np.eye(n_months), n=2, axis=0)
        stacked = np.vstack(
            [
                policy.prior_weight * np.eye(n_months),
                policy.incumbent_weight * np.eye(n_months),
                policy.first_difference_weight * first,
                policy.second_difference_weight * second,
            ]
        )
        target = np.r_[
            policy.prior_weight * prior,
            policy.incumbent_weight * incumbent,
            policy.first_difference_weight * (first @ prior),
            policy.second_difference_weight * (second @ prior),
        ]
        quadratic = stacked.T @ stacked + np.eye(n_months) * 1e-10
        return quadratic, stacked.T @ target

    def solve_exact(
        self,
        windows: np.ndarray,
        national: np.ndarray,
        incumbent: np.ndarray,
        cap: float,
    ) -> np.ndarray:
        """Exact windows, bounded month-to-month ratios.

        Raises
        ------
        RegularizationError
            If the windows are incompatible with the cap or the solver
            leaves growth violations.
        """
        design, offset, lower, scale, _ = self._scaled(windows)
        growth = growth_matrix(design.shape[0], cap)
        offset_scaled = offset / scale
        prior = window_prior(windows, national)
        quadratic, linear = self._objective(prior, incumbent, scale)
        reduced_quadratic = design.T @ quadratic @ design
        reduced_linear = design.T @ (linear - quadratic @ offset_scaled)
        total = WINDOW_LENGTH * float(windows[0] / scale)
        start = self._exact_feasibility(windows, cap)
        if not start.success:
            raise RegularizationError("Exact windows incompatible with cap")
        result = minimize(
            lambda z: 0.5 * z @ (reduced_quadratic @ z) - reduced_linear @ z,
            start.x,
            jac=lambda z: reduced_quadratic @ z - reduced_linear,
            bounds=Bounds(lower / scale, np.full(WINDOW_LENGTH, np.inf)),
            constraints=[
                LinearConstraint(np.ones((1, WINDOW_LENGTH)), total, total),
                LinearConstraint(
                    growth @ design, -np.inf, -growth @ offset_scaled
                ),
            ],
            method="SLSQP",
            options={
                "maxiter": self._policy.exact_solver_max_iterations,
                "ftol": self._policy.exact_solver_tolerance,
            },
        )
        monthly = scale * (design @ result.x + offset_scaled)
        if not result.success and np.max(growth @ monthly) > _GROWTH_TOLERANCE:
            raise RegularizationError(f"Exact solver failed: {result.message}")
        return np.asarray(monthly)

    def solve_soft(
        self,
        windows: np.ndarray,
        national: np.ndarray,
        incumbent: np.ndarray,
        tolerance: float,
        cap: float,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Windows within ``tolerance``, bounded month-to-month ratios.

        Raises
        ------
        RegularizationError
            If neither the solver nor its feasible LP start satisfies the
            constraints.
        """
        _, _, _, scale, rolling = self._scaled(windows)
        normalized = windows / scale
        n_months = rolling.shape[1]
        growth = growth_matrix(n_months, cap)
        floor = self._policy.relative_floor * float(np.min(normalized))
        prior = window_prior(windows, national)
        quadratic, linear = self._objective(prior, incumbent, scale)
        constraints = [
            LinearConstraint(
                np.r_[rolling, growth],
                np.r_[
                    normalized * (1 - tolerance), np.full(len(growth), -np.inf)
                ],
                np.r_[normalized * (1 + tolerance), np.zeros(len(growth))],
            )
        ]
        start = linprog(
            np.zeros(n_months),
            A_ub=np.r_[rolling, -rolling, growth],
            b_ub=np.r_[
                normalized * (1 + tolerance),
                -normalized * (1 - tolerance),
                np.zeros(len(growth)),
            ],
            bounds=[(floor, None)] * n_months,
            method="highs",
        )
        if not start.success:
            raise RegularizationError(f"Soft LP infeasible: {start.message}")
        result = minimize(
            lambda z: 0.5 * z @ (quadratic @ z) - linear @ z,
            start.x,
            method="SLSQP",
            jac=lambda z: quadratic @ z - linear,
            bounds=Bounds(np.full(n_months, floor), np.full(n_months, np.inf)),
            constraints=constraints,
            options={
                "maxiter": self._policy.soft_solver_max_iterations,
                "ftol": self._policy.soft_solver_tolerance,
            },
        )
        values = result.x * scale
        fallback = False
        window_gap = float(np.max(abs((rolling @ values - windows) / windows)))
        growth_gap = float(np.max(growth @ values))
        if (
            window_gap > tolerance + _WINDOW_TOLERANCE
            or growth_gap > _GROWTH_TOLERANCE
            or min(values) < floor * scale - _FLOOR_TOLERANCE
        ):
            if not result.success:
                values = start.x * scale
                fallback = True
                window_gap = float(
                    np.max(abs((rolling @ values - windows) / windows))
                )
                growth_gap = float(np.max(growth @ values))
            if (
                window_gap > tolerance + _WINDOW_TOLERANCE
                or growth_gap > _GROWTH_TOLERANCE
            ):
                raise RegularizationError("Soft solution infeasible")
        return np.asarray(values), {
            "solver_message": str(result.message),
            "solver_success": bool(result.success),
            "window_tolerance": float(tolerance),
            "lp_fallback": fallback,
        }

    def adapted_cap(self, windows: np.ndarray) -> float:
        """Smallest cap whose minimum window tolerance fits the limit."""
        policy = self._policy
        low, high = policy.flexible_cap_lower, policy.max_monthly_ratio
        for _ in range(policy.flexible_bisection_steps):
            middle = (low + high) / 2
            if (
                self.min_window_tolerance(windows, middle)
                <= policy.max_flexible_window_tolerance
            ):
                high = middle
            else:
                low = middle
        return min(policy.max_monthly_ratio, high + policy.flexible_cap_buffer)


@dataclass(frozen=True)
class RegularizationResult:
    """Strict and filtered panels, predictor bases and audits."""

    strict_panel: pd.DataFrame
    strict_predictors: pd.DataFrame
    filtered_panel: pd.DataFrame
    filtered_predictors: pd.DataFrame
    city_comparison: pd.DataFrame
    filter_decisions: pd.DataFrame
    filtered_windows: pd.DataFrame


def _replace_target(
    panel: pd.DataFrame, rows: pd.Index, values: np.ndarray
) -> None:
    panel.loc[rows, TARGET] = values
    panel.loc[rows, "labor_force"] = (
        np.array(panel.loc[rows, "employed"], dtype=float) + values
    )
    panel.loc[rows, "working_age"] = np.array(
        panel.loc[rows, "labor_force"], dtype=float
    ) + np.array(panel.loc[rows, "inactive"], dtype=float)


class UrbanQualityScenarios:
    """Build the strict and quality-filtered urban scenarios."""

    def __init__(
        self,
        policy: RegularizationPolicy,
        synthetic_code: int,
        first_month: str,
    ) -> None:
        """Compose the regularizer."""
        self._policy = policy
        self._regularizer = JumpRegularizer(policy)
        self._synthetic = synthetic_code
        self._first = first_month

    def run(
        self,
        panel: pd.DataFrame,
        predictors: pd.DataFrame,
        windows: Mapping[str, Mapping[str, np.ndarray]],
        national: pd.DataFrame,
    ) -> RegularizationResult:
        """Return both scenarios with their audits."""
        policy = self._policy
        reference = national.set_index("period")
        strict = panel.copy()
        filtered = panel.copy()
        comparison, decisions, window_rows = [], [], []
        codes = dict(zip(panel["city_name"], panel["city_code"], strict=False))
        for name, city_windows in windows.items():
            code = int(codes[name])
            rows = panel.index[
                (panel["city_code"] == code) & (panel["period"] >= self._first)
            ]
            months = list(panel.loc[rows, "period"])
            published = np.asarray(city_windows[TARGET], dtype=float)
            national_target = np.array(
                reference.loc[months, TARGET], dtype=float
            )
            original = np.array(panel.loc[rows, TARGET], dtype=float)
            before = jump_metrics(original, policy.max_monthly_ratio)
            min_tolerance = self._regularizer.min_window_tolerance(
                published, policy.max_monthly_ratio
            )
            unchanged = (
                before["months_increase_above_cap"] == 0
                and before["bidirectional_above_cap"] == 0
            )
            exact_cap = self._regularizer.min_exact_cap(published)
            strict_cap = (
                max(
                    policy.max_monthly_ratio,
                    exact_cap * (1 + policy.strict_cap_buffer),
                )
                if exact_cap > policy.max_monthly_ratio + 1e-6
                else policy.max_monthly_ratio
            )
            strict_values = (
                original.copy()
                if unchanged
                else self._regularizer.solve_exact(
                    published, national_target, original, strict_cap
                )
            )
            _replace_target(strict, rows, strict_values)

            info: dict[str, Any] = {}
            if code in set(policy.flexible_codes):
                rule = RULE_FLEXIBLE
                cap = self._regularizer.adapted_cap(published)
                filtered_values, info = self._regularizer.solve_soft(
                    published,
                    national_target,
                    original,
                    policy.max_flexible_window_tolerance,
                    cap,
                )
                info["adapted_cap"] = cap
            elif unchanged:
                rule = RULE_UNCHANGED
                filtered_values = original.copy()
            else:
                rule = RULE_STRICT
                filtered_values = strict_values
            _replace_target(filtered, rows, filtered_values)

            rolling = window_matrix(len(published))
            strict_error = (rolling @ strict_values - published) / published
            comparison.append(
                {
                    "city_code": code,
                    "city_name": name,
                    "unchanged": bool(unchanged),
                    "min_window_tolerance_pct": 100 * min_tolerance,
                    "min_exact_cap": float(exact_cap),
                    "strict_cap_used": float(strict_cap),
                    "strict_max_window_error_pct": float(
                        100 * np.max(np.abs(strict_error))
                    ),
                    **{f"before_{k}": v for k, v in before.items()},
                    **{
                        f"strict_{k}": v
                        for k, v in jump_metrics(
                            strict_values, policy.max_monthly_ratio
                        ).items()
                    },
                }
            )
            fitted = rolling @ filtered_values
            window_error = float(
                np.max(np.abs(fitted - published) / published)
            )
            limit = (
                policy.max_flexible_window_tolerance
                if rule == RULE_FLEXIBLE
                else 1e-5
            )
            if window_error > limit + (1e-8 if rule == RULE_FLEXIBLE else 0):
                raise RegularizationError(
                    f"Window tolerance exceeded in {name}"
                )
            ratios = np.maximum(
                filtered_values[1:] / filtered_values[:-1],
                filtered_values[:-1] / filtered_values[1:],
            )
            if np.max(ratios) > policy.max_monthly_ratio + 1e-6:
                raise RegularizationError(f"Jump cap violated in {name}")
            for end, observed, estimate in zip(
                months[WINDOW_LENGTH - 1 :], published, fitted, strict=True
            ):
                window_rows.append(
                    {
                        "city_code": code,
                        "city_name": name,
                        "window_end": end,
                        "published_mean": float(observed),
                        "filtered_mean": float(estimate),
                        "difference_persons": float(estimate - observed),
                        "relative_error_pct": float(
                            100 * (estimate - observed) / observed
                        ),
                        "rule": rule,
                    }
                )
            decisions.append(
                {
                    "city_code": code,
                    "city_name": name,
                    "rule": rule,
                    "max_window_error_pct": 100 * window_error,
                    "max_bidirectional_ratio": float(np.max(ratios)),
                    "max_change_persons": float(
                        np.max(np.abs(filtered_values - original))
                    ),
                    "adapted_cap": info.get("adapted_cap"),
                    "lp_fallback": info.get("lp_fallback"),
                }
            )
        decisions.append(
            {
                "city_code": self._synthetic,
                "city_name": str(
                    panel.loc[
                        panel["city_code"] == self._synthetic, "city_name"
                    ].iloc[0]
                ),
                "rule": RULE_SYNTHETIC,
                "max_change_persons": 0.0,
            }
        )
        self._verify(panel, strict)
        self._verify(panel, filtered)
        return RegularizationResult(
            strict_panel=strict,
            strict_predictors=self._predictors(predictors, strict),
            filtered_panel=filtered,
            filtered_predictors=self._predictors(predictors, filtered),
            city_comparison=pd.DataFrame(comparison),
            filter_decisions=pd.DataFrame(decisions),
            filtered_windows=pd.DataFrame(window_rows),
        )

    @staticmethod
    def _predictors(base: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
        keys = ["city_code", "period"]
        joined = panel.set_index(keys)
        result = base.copy()
        index = pd.MultiIndex.from_frame(base[keys])
        for field in FIELDS:
            result[field] = np.array(index.map(joined[field]), dtype=float)
        return with_urban_rates(result)

    def _verify(self, original: pd.DataFrame, scenario: pd.DataFrame) -> None:
        if (
            max(
                float(
                    (
                        scenario["labor_force"]
                        - scenario["employed"]
                        - scenario["unemployed"]
                    )
                    .abs()
                    .max()
                ),
                float(
                    (
                        scenario["working_age"]
                        - scenario["labor_force"]
                        - scenario["inactive"]
                    )
                    .abs()
                    .max()
                ),
            )
            >= _IDENTITY_TOLERANCE
        ):
            raise RegularizationError("Identities not closed")
        if (
            scenario["working_age"]
            > scenario["population"] + _IDENTITY_TOLERANCE
        ).any():
            raise RegularizationError("Working age above population")
        protected = (original["period"] < self._first) | (
            original["city_code"] == self._synthetic
        )
        if not np.array_equal(
            np.array(scenario.loc[protected, list(FIELDS)]),
            np.array(original.loc[protected, list(FIELDS)]),
        ):
            raise RegularizationError("Protected months were modified")
