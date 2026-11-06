"""Latent monthly urban values from published 12-month rolling windows.

Since 2021 DANE publishes, for 32 cities, means over 12-month rolling
windows, not monthly values. With 68 months and 57 windows, the window
means fix every month up to twelve free base values: ``y = H z + b``. The
free values are chosen by a strictly convex quadratic program that keeps
the months close to a prior (the national homologous series scaled by the
city/national window ratio), penalizes jagged first differences and softly
links January 2021 to December 2020; the sum constraint reproduces every
window exactly. These months are latent estimates, never DANE monthly data.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from icml.national.geih_annex import (
    extract_region_quantities,
    parse_labor_blocks,
)

WINDOW_LENGTH = 12
FIT_COMPONENTS: tuple[str, ...] = (
    "employed",
    "unemployed",
    "inactive",
    "population",
)
_SINGULAR_REGULARIZATION = 1e-9
_LOWER_TOLERANCE = 1e-9
_EXACT_TOLERANCE_PERSONS = 2e-5
_NEGATIVE_TOLERANCE = 1e-6
_FEASIBILITY_TOLERANCE = 1e-8
_SOLVER_VIOLATION = 1e-7


class WindowFitError(ValueError):
    """Raised when windows cannot be reproduced under the constraints."""


@dataclass(frozen=True)
class WindowSheetSpec:
    """Layout of the rolling-window sheet of the monthly annex."""

    sheet_name: str
    first_window_end: str
    n_windows: int
    block_marker: str
    block_end_marker: str
    scale_factor: float
    concepts: Mapping[str, str]


@dataclass(frozen=True)
class WindowFitPolicy:
    """Prior, smoothness and floor settings of the latent fit."""

    first_month: str
    last_month: str
    smoothness_weight: float
    bridge_weight: float
    relative_floor: float
    solver_tolerance: float
    solver_max_iterations: int

    def months(self) -> pd.PeriodIndex:
        """Return the latent months."""
        return pd.period_range(self.first_month, self.last_month, freq="M")


def read_rolling_windows(
    path: Path, spec: WindowSheetSpec
) -> dict[str, dict[str, np.ndarray]]:
    """Read every city's window means (persons) from the annex.

    Raises
    ------
    WindowFitError
        If a city has fewer than ``n_windows`` complete windows.
    """
    cells = pd.read_excel(path, sheet_name=spec.sheet_name, header=None)
    blocks = parse_labor_blocks(
        cells,
        start_period=spec.first_window_end,
        block_marker=spec.block_marker,
        block_end_marker=spec.block_end_marker,
        value_decimals=None,
    )
    windows: dict[str, dict[str, np.ndarray]] = {}
    for region in blocks["region"].drop_duplicates():
        wide = extract_region_quantities(
            blocks,
            region=str(region),
            concepts=spec.concepts,
            scale_factor=spec.scale_factor,
        )
        if len(wide) < spec.n_windows:
            raise WindowFitError(f"{region}: {len(wide)} windows found")
        # A later annex carries more windows than a vintage uses; the
        # first n_windows are the vintage's own, so a past vintage can be
        # replayed from the current file.
        wide = wide.iloc[: spec.n_windows]
        windows[str(region)] = {
            q: np.array(wide[q], dtype=float) for q in spec.concepts.values()
        }
    return windows


def rolling_design(
    windows: np.ndarray, relative_floor: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``H``, ``b`` and the base lower bounds for ``y = H z + b``.

    Every month equals one of the twelve 2021 base months plus the
    cumulative change implied by consecutive windows. The lower bounds keep
    each month above ``relative_floor`` times the smallest window, which
    prevents algebraic compensation from producing near-zero months.
    """
    n_windows = len(windows)
    n_months = n_windows + WINDOW_LENGTH - 1
    design = np.zeros((n_months, WINDOW_LENGTH))
    offset = np.zeros(n_months)
    for month in range(n_months):
        design[month, month % WINDOW_LENGTH] = 1
        if month >= WINDOW_LENGTH:
            first = month - WINDOW_LENGTH + 1
            offset[month] = offset[month - WINDOW_LENGTH] + WINDOW_LENGTH * (
                windows[first] - windows[first - 1]
            )
    floor = relative_floor * float(np.min(windows))
    lower = np.array(
        [
            max(0.0, floor - float(np.min(offset[k::WINDOW_LENGTH])))
            for k in range(WINDOW_LENGTH)
        ]
    )
    return design, offset, lower


def window_prior(windows: np.ndarray, national: np.ndarray) -> np.ndarray:
    """National months scaled by the city/national window ratio.

    The ratio of the first window is used for the first eleven months.

    Raises
    ------
    WindowFitError
        If the national rolling means are not positive.
    """
    national_rolling = np.convolve(
        national, np.ones(WINDOW_LENGTH) / WINDOW_LENGTH, "valid"
    )
    if not np.all(national_rolling > 0):
        raise WindowFitError("National signal must be positive")
    ratios = windows / national_rolling
    extended = np.r_[np.repeat(ratios[0], WINDOW_LENGTH - 1), ratios]
    return np.asarray(national * extended)


class LatentWindowFit:
    """Fit latent months that reproduce the windows exactly."""

    def __init__(self, policy: WindowFitPolicy) -> None:
        """Store the policy."""
        self._policy = policy

    def fit(
        self,
        windows: np.ndarray,
        national: np.ndarray,
        previous_value: float,
        previous_national: float,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Return the latent months and fit diagnostics.

        Raises
        ------
        WindowFitError
            If windows are incompatible with non-negativity or the result
            does not reproduce them.
        """
        policy = self._policy
        design, offset, lower = rolling_design(windows, policy.relative_floor)
        scale = float(windows[0])
        if scale <= 0:
            raise WindowFitError("Windows must be positive")
        prior = window_prior(windows, national)
        offset_scaled, prior_scaled = offset / scale, prior / scale
        lower_scaled = lower / scale
        n_months = len(prior)
        difference = np.diff(np.eye(n_months), axis=0)
        smooth = np.sqrt(policy.smoothness_weight)
        matrix = np.r_[design, smooth * (difference @ design)]
        target = np.r_[
            prior_scaled - offset_scaled,
            smooth * (difference @ (prior_scaled - offset_scaled)),
        ]
        bridge = previous_value * national[0] / previous_national / scale
        row = np.zeros((1, WINDOW_LENGTH))
        row[0, 0] = np.sqrt(policy.bridge_weight)
        matrix = np.r_[matrix, row]
        target = np.r_[target, [np.sqrt(policy.bridge_weight) * bridge]]
        quadratic = (
            matrix.T @ matrix
            + np.eye(WINDOW_LENGTH) * _SINGULAR_REGULARIZATION
        )
        linear = matrix.T @ target
        system = np.zeros((WINDOW_LENGTH + 1, WINDOW_LENGTH + 1))
        system[:WINDOW_LENGTH, :WINDOW_LENGTH] = quadratic
        system[:WINDOW_LENGTH, WINDOW_LENGTH] = 1
        system[WINDOW_LENGTH, :WINDOW_LENGTH] = 1
        solution = np.linalg.solve(system, np.r_[linear, float(WINDOW_LENGTH)])
        solution = solution[:WINDOW_LENGTH]
        bounded = bool(np.any(solution < lower_scaled - _LOWER_TOLERANCE))
        if bounded:
            solution = self._bounded(quadratic, linear, lower_scaled)
        months = scale * (design @ solution + offset_scaled)
        rolling = np.convolve(
            months, np.ones(WINDOW_LENGTH) / WINDOW_LENGTH, mode="valid"
        )
        error = float(np.max(np.abs(rolling - windows)))
        if error > _EXACT_TOLERANCE_PERSONS:
            raise WindowFitError(f"Windows not reproduced: {error}")
        if np.min(months) < -_NEGATIVE_TOLERANCE:
            raise WindowFitError("Negative latent month")
        return months, {
            "max_window_error_persons": error,
            "minimum_month": float(months.min()),
            "lower_bound_active": bounded,
            "prior_wape_pct": float(
                100 * np.sum(np.abs(months - prior)) / np.sum(np.abs(prior))
            ),
        }

    def _bounded(
        self, quadratic: np.ndarray, linear: np.ndarray, lower: np.ndarray
    ) -> np.ndarray:
        slack = WINDOW_LENGTH - lower.sum()
        if slack < -_FEASIBILITY_TOLERANCE:
            raise WindowFitError("Windows incompatible with non-negativity")
        start = lower + max(0.0, slack) / WINDOW_LENGTH
        result = minimize(
            lambda x: 0.5 * x @ quadratic @ x - linear @ x,
            start,
            jac=lambda x: quadratic @ x - linear,
            bounds=[(float(v), None) for v in lower],
            constraints=[
                {
                    "type": "eq",
                    "fun": lambda x: np.sum(x) - WINDOW_LENGTH,
                    "jac": lambda x: np.ones(WINDOW_LENGTH),
                }
            ],
            method="SLSQP",
            options={
                "ftol": self._policy.solver_tolerance,
                "maxiter": self._policy.solver_max_iterations,
            },
        )
        if (
            not result.success
            and max(0.0, -np.min(result.x - lower)) > _SOLVER_VIOLATION
        ):
            raise WindowFitError(f"Bounded fit failed: {result.message}")
        return np.asarray(result.x)


def rolling_means(values: np.ndarray) -> np.ndarray:
    """Return the 12-month rolling means of a monthly vector."""
    return np.convolve(
        values, np.ones(WINDOW_LENGTH) / WINDOW_LENGTH, mode="valid"
    )


def as_matrix(
    windows: Mapping[str, np.ndarray], order: Sequence[str]
) -> np.ndarray:
    """Stack window vectors in a fixed quantity order."""
    return np.vstack([windows[q] for q in order])
