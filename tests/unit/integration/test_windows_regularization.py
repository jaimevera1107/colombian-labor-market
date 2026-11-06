import numpy as np
import pytest

from icml.integration.regularization import (
    JumpRegularizer,
    RegularizationPolicy,
    growth_matrix,
    jump_metrics,
    window_matrix,
)
from icml.integration.windows import (
    LatentWindowFit,
    WindowFitPolicy,
    rolling_design,
    rolling_means,
    window_prior,
)

FIT = WindowFitPolicy(
    first_month="2021-01",
    last_month="2022-12",
    smoothness_weight=0.65,
    bridge_weight=0.12,
    relative_floor=0.10,
    solver_tolerance=1e-12,
    solver_max_iterations=900,
)
REGULARIZATION = RegularizationPolicy(
    max_monthly_ratio=2.0,
    relative_floor=0.10,
    tolerance_margin=0.0025,
    strict_cap_buffer=0.0075,
    cap_bisection_steps=27,
    flexible_codes=[],
    max_flexible_window_tolerance=0.021,
    flexible_cap_buffer=0.015,
    flexible_cap_lower=1.0001,
    flexible_bisection_steps=22,
    prior_weight=0.80,
    incumbent_weight=0.30,
    first_difference_weight=0.70,
    second_difference_weight=0.45,
    exact_solver_tolerance=1e-11,
    exact_solver_max_iterations=500,
    soft_solver_tolerance=1e-10,
    soft_solver_max_iterations=400,
)


def _monthly(n=24, seed=3):
    rng = np.random.default_rng(seed)
    season = 1 + 0.1 * np.sin(2 * np.pi * np.arange(n) / 12)
    return 1000 * season * (1 + 0.02 * rng.standard_normal(n))


def test_design_reproduces_any_series_with_matching_base():
    months = _monthly()
    windows = rolling_means(months)
    design, offset, lower = rolling_design(windows, 0.10)
    np.testing.assert_allclose(design @ months[:12] + offset, months)
    assert (lower >= 0).all()


def test_prior_reproduces_windows_when_city_is_proportional():
    national = _monthly(seed=5)
    windows = rolling_means(0.3 * national)
    np.testing.assert_allclose(window_prior(windows, national), 0.3 * national)


def test_latent_fit_reproduces_windows_exactly():
    national = _monthly(seed=7)
    truth = 0.2 * _monthly(seed=8)
    windows = rolling_means(truth)
    months, diagnostics = LatentWindowFit(FIT).fit(
        windows,
        national,
        previous_value=float(truth[0]),
        previous_national=float(national[0]),
    )
    np.testing.assert_allclose(rolling_means(months), windows, atol=2e-5)
    assert diagnostics["max_window_error_persons"] < 2e-5
    assert months.min() > 0


def test_growth_and_window_operators():
    growth = growth_matrix(3, 2.0)
    assert (growth @ np.array([1.0, 2.0, 4.0]) <= 0).all()
    assert (growth @ np.array([1.0, 3.0, 3.0]) > 0).any()
    assert window_matrix(2).shape == (2, 13)
    metrics = jump_metrics(np.array([1.0, 3.0, 1.0]), 2.0)
    assert metrics["months_increase_above_cap"] == 1
    assert metrics["bidirectional_above_cap"] == 2


def test_exact_regularization_keeps_windows_and_bounds_jumps():
    national = _monthly(n=36, seed=9)
    jagged = 0.1 * national * np.where(np.arange(36) % 6 == 0, 3.5, 1.0)
    windows = rolling_means(jagged)
    regularizer = JumpRegularizer(REGULARIZATION)
    cap = max(2.0, regularizer.min_exact_cap(windows) * 1.0075)
    smoothed = regularizer.solve_exact(windows, national, jagged, cap)
    np.testing.assert_allclose(rolling_means(smoothed), windows, rtol=1e-6)
    ratios = np.maximum(
        smoothed[1:] / smoothed[:-1], smoothed[:-1] / smoothed[1:]
    )
    assert ratios.max() <= cap + 1e-6


def test_soft_regularization_respects_tolerance():
    national = _monthly(n=36, seed=11)
    jagged = 0.1 * national * np.where(np.arange(36) % 5 == 0, 4.0, 1.0)
    windows = rolling_means(jagged)
    regularizer = JumpRegularizer(REGULARIZATION)
    values, info = regularizer.solve_soft(
        windows, national, jagged, tolerance=0.05, cap=2.0
    )
    relative = np.abs(rolling_means(values) - windows) / windows
    assert relative.max() <= 0.05 + 1e-6
    assert info["window_tolerance"] == pytest.approx(0.05)
