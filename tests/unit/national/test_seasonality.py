import numpy as np
import pandas as pd
import pytest

from icml.national.seasonality import (
    SeasonalityError,
    SeasonalityPolicy,
    SeasonalPatternTransfer,
    proportional_fit,
)

QUANTITIES = [
    "population",
    "working_age",
    "labor_force",
    "employed",
    "unemployed",
    "inactive",
]


def _policy(strength):
    return SeasonalityPolicy(
        history_start=1996,
        history_end=1998,
        template_from=1999,
        template_through=2000,
        strength=strength,
        seasonal_window=13,
        trend_window=19,
        ipf_tolerance=2e-7,
        ipf_max_iterations=10000,
        max_relative_monthly_intervention=0.15,
        max_added_splice_log=0.06,
    )


def _windows(monthly_levels):
    # Template must span 36 months for STL: extend observed to 2001.
    extra = monthly_levels.iloc[-12:].copy()
    extra["period"] = pd.period_range("2001-01", periods=12, freq="M").astype(
        str
    )
    observed = pd.concat([monthly_levels, extra], ignore_index=True)
    return monthly_levels, observed


def test_proportional_fit_matches_both_margins():
    seed = np.array([[15.0, 2.0, 5.0], [18.0, 3.0, 8.0], [21.0, 4.0, 5.0]])
    fitted, iterations = proportional_fit(
        seed * 1.1,
        seed.sum(axis=1),
        seed.sum(axis=0),
        tolerance=1e-9,
        max_iterations=1000,
    )
    assert iterations >= 1
    np.testing.assert_allclose(fitted.sum(axis=1), seed.sum(axis=1), atol=1e-8)
    np.testing.assert_allclose(fitted.sum(axis=0), seed.sum(axis=0), atol=1e-8)


def test_proportional_fit_rejects_invalid_margins():
    seed = np.ones((2, 2))
    with pytest.raises(SeasonalityError, match="incompatible"):
        proportional_fit(
            seed,
            np.array([1.0, 1.0]),
            np.array([5.0, 5.0]),
            tolerance=1e-9,
            max_iterations=10,
        )
    with pytest.raises(SeasonalityError, match="positive"):
        proportional_fit(
            -seed, np.ones(2), np.ones(2), tolerance=1e-9, max_iterations=10
        )


def test_zero_strength_is_identity(monthly_levels):
    history = monthly_levels[monthly_levels["period"] < "1999-01"]
    template_source = pd.concat(
        [
            monthly_levels,
            monthly_levels.iloc[-12:].assign(
                period=pd.period_range("2001-01", periods=12, freq="M").astype(
                    str
                )
            ),
        ],
        ignore_index=True,
    )
    policy = SeasonalityPolicy(
        history_start=1996,
        history_end=1998,
        template_from=1999,
        template_through=2001,
        strength=0.0,
        seasonal_window=13,
        trend_window=19,
        ipf_tolerance=2e-7,
        ipf_max_iterations=10000,
        max_relative_monthly_intervention=0.15,
        max_added_splice_log=0.06,
    )
    result = SeasonalPatternTransfer(policy).adjust(history, template_source)
    np.testing.assert_allclose(
        result.monthly[QUANTITIES], history[QUANTITIES], rtol=1e-9
    )


def test_adjustment_preserves_annual_means_and_identities(monthly_levels):
    history = monthly_levels[monthly_levels["period"] < "1999-01"]
    template_source = pd.concat(
        [
            monthly_levels,
            monthly_levels.iloc[-12:].assign(
                period=pd.period_range("2001-01", periods=12, freq="M").astype(
                    str
                )
            ),
        ],
        ignore_index=True,
    )
    policy = SeasonalityPolicy(
        history_start=1996,
        history_end=1998,
        template_from=1999,
        template_through=2001,
        strength=1.0,
        seasonal_window=13,
        trend_window=19,
        ipf_tolerance=2e-7,
        ipf_max_iterations=10000,
        max_relative_monthly_intervention=0.15,
        max_added_splice_log=0.06,
    )
    result = SeasonalPatternTransfer(policy).adjust(history, template_source)
    assert result.quality["identities_closed"]
    assert result.quality["annual_anchors_preserved"]
    np.testing.assert_allclose(
        result.monthly["working_age"], history["working_age"], rtol=1e-12
    )


def test_policy_and_window_validation(monthly_levels):
    with pytest.raises(ValueError, match="strength"):
        _policy(1.5)
    with pytest.raises(SeasonalityError, match="Template"):
        SeasonalPatternTransfer(_policy(0.5)).adjust(
            monthly_levels, monthly_levels.iloc[:-6]
        )
