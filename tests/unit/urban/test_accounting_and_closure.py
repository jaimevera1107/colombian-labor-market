import numpy as np
import pandas as pd
import pytest

from icml.urban.accounting import (
    AccountingProjectionError,
    project_signals,
)
from icml.urban.closure import BridgePolicy, ClosureError, close_bridge


def _coherent(employed, unemployed, inactive, outside):
    labor_force = employed + unemployed
    working_age = labor_force + inactive
    return np.array(
        [
            employed,
            unemployed,
            inactive,
            labor_force,
            working_age,
            working_age + outside,
        ],
        dtype=float,
    )


def test_coherent_signals_are_unchanged():
    signals = _coherent(100.0, 10.0, 60.0, 50.0)
    projected = project_signals(signals[None, :], signals)
    np.testing.assert_allclose(projected[0], signals, rtol=1e-12)


def test_projection_closes_identities_and_keeps_means():
    rng = np.random.default_rng(1)
    base = _coherent(100.0, 10.0, 60.0, 50.0)
    noisy = base * (1 + 0.01 * rng.standard_normal((12, 6)))
    projected = project_signals(noisy, base)
    np.testing.assert_allclose(
        projected[:, 3], projected[:, 0] + projected[:, 1]
    )
    np.testing.assert_allclose(
        projected[:, 4], projected[:, 3] + projected[:, 2]
    )
    coherent_block = (
        np.tile(base, (12, 1)) * np.linspace(0.9, 1.1, 12)[:, None]
    )
    np.testing.assert_allclose(
        project_signals(coherent_block, base).mean(axis=0),
        coherent_block.mean(axis=0),
        rtol=1e-12,
    )


def test_projection_rejects_bad_inputs():
    with pytest.raises(AccountingProjectionError):
        project_signals(np.ones((2, 5)), np.ones(6))
    with pytest.raises(AccountingProjectionError):
        project_signals(np.ones((2, 6)), -np.ones(6))
    impossible = _coherent(100.0, 10.0, 60.0, 50.0)
    impossible[5] = 1.0  # population far below working age
    with pytest.raises(AccountingProjectionError, match="negative"):
        project_signals(impossible[None, :], np.ones(6))


POLICY = BridgePolicy(
    start_year=2015,
    end_year=2020,
    target_mean_log=0.08,
    max_terminal_log_change=0.17,
    max_extra_log_growth=0.03,
    tolerance=1e-10,
)


def _trajectory(level=1.0):
    years = range(2007, 2021)
    rows = {
        y: _coherent(100 * level, 10 * level, 60 * level, 50 * level)
        for y in years
    }
    return pd.DataFrame.from_dict(
        rows,
        orient="index",
        columns=[
            "employed",
            "unemployed",
            "inactive",
            "labor_force",
            "working_age",
            "population",
        ],
    )


def test_bridge_shrinks_seam_and_keeps_early_years():
    trajectory = _trajectory()
    donor = _trajectory().reindex(range(2007, 2022)).ffill()
    proxies = _trajectory(1.12).reindex([2021]).ffill()
    proxies.loc[2021] = _trajectory(1.12).iloc[0]
    adjusted, diagnostics = close_bridge(
        trajectory, proxies, donor, POLICY, seam_year=2021
    )
    assert diagnostics["seam_before"] > 0.08
    assert diagnostics["target_met"]
    assert diagnostics["untouched_before_ramp"]
    assert diagnostics["coherent"]
    pd.testing.assert_frame_equal(adjusted.loc[:2014], trajectory.loc[:2014])


def test_bridge_below_target_is_identity():
    trajectory = _trajectory()
    donor = _trajectory().reindex(range(2007, 2022)).ffill()
    proxies = pd.DataFrame([_trajectory(1.01).iloc[0]], index=[2021])
    adjusted, diagnostics = close_bridge(
        trajectory, proxies, donor, POLICY, seam_year=2021
    )
    assert diagnostics["max_delta_log"] == 0
    pd.testing.assert_frame_equal(adjusted, trajectory, check_dtype=False)


def test_bridge_rejects_excessive_growth():
    strict = BridgePolicy(
        start_year=2015,
        end_year=2020,
        target_mean_log=0.0,
        max_terminal_log_change=0.5,
        max_extra_log_growth=0.01,
        tolerance=1e-10,
    )
    trajectory = _trajectory()
    donor = _trajectory().reindex(range(2007, 2022)).ffill()
    proxies = pd.DataFrame([_trajectory(1.3).iloc[0]], index=[2021])
    with pytest.raises(ClosureError, match="limit"):
        close_bridge(trajectory, proxies, donor, strict, seam_year=2021)
