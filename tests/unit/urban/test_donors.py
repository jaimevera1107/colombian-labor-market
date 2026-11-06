import numpy as np
import pandas as pd
import pytest

from icml.urban.donors import (
    DonorPolicy,
    DonorTransfer,
    pair_features,
    pareto_efficient,
)
from icml.urban.inputs import UrbanSources

QUANTITIES = [
    "employed",
    "unemployed",
    "inactive",
    "labor_force",
    "working_age",
    "population",
]


def _frame(years, scale, growth):
    rows = []
    for k, year in enumerate(years):
        factor = scale * (1 + growth) ** k
        employed, unemployed, inactive, outside = (
            100 * factor,
            12 * factor,
            60 * factor,
            40 * factor,
        )
        labor_force = employed + unemployed
        working_age = labor_force + inactive
        rows.append(
            [
                year,
                employed,
                unemployed,
                inactive,
                labor_force,
                working_age,
                working_age + outside,
            ]
        )
    return pd.DataFrame(rows, columns=["year", *QUANTITIES]).set_index("year")


def _policy():
    return DonorPolicy(
        recipient_codes=[2],
        excluded_codes=[],
        selection_years=[2021, 2022],
        holdout_year=2023,
        seam_year=2021,
        history_start=2018,
        history_end=2020,
        proxy_last_year=2023,
        published_unit_persons=1.0,
        guard_tolerance_log=0.03,
        validation_quantile=0.95,
        pareto_tolerance=1e-12,
        tie_break_weights=[0.2] * 5,
        minimax_weight=0.1,
        incumbent_score_weights=[0.2] * 5,
        normalization_low_quantile=0.1,
        normalization_high_quantile=0.9,
        normalization_min_scale=1e-10,
    )


def test_pareto_mask_flags_dominated_rows():
    losses = np.array([[1.0, 1.0], [2.0, 2.0], [0.5, 3.0]])
    assert pareto_efficient(losses, 1e-12).tolist() == [True, False, True]
    with pytest.raises(ValueError):
        pareto_efficient(np.array([1.0, 2.0]), 1e-12)


def test_identical_dynamics_have_zero_growth_and_rate_loss():
    years = [2021, 2022, 2023]
    features = pair_features(
        _frame(years, 1.0, 0.02), _frame(years, 3.0, 0.02)
    )
    assert features[0] == pytest.approx(0.0, abs=1e-12)
    assert features[2] == pytest.approx(0.0, abs=1e-12)
    assert features[3] == pytest.approx(np.log(3.0))
    assert features[4] == pytest.approx(0.0, abs=1e-12)


def test_transfer_rescales_donor_to_recipient_level():
    years = list(range(2018, 2024))
    donor = _frame(years, 1.0, 0.03)
    recipient = _frame(years, 0.25, 0.03)
    sources = UrbanSources(
        history={1: donor},
        proxies={2: recipient, 1: donor},
        raw_history=pd.DataFrame(),
    )
    transfer = DonorTransfer(sources, _policy())
    predicted = transfer.predict(2, 1, [2018, 2019, 2020])
    np.testing.assert_allclose(
        predicted["employed"], recipient.loc[2018:2020, "employed"]
    )
    checks = transfer.checks(2, 1)
    assert checks["holdout_error_mean"] == pytest.approx(0.0, abs=1e-12)
    assert checks["working_age_below_population"]


def test_policy_requires_five_weights():
    with pytest.raises(ValueError, match="weight"):
        DonorPolicy(**{**_policy().__dict__, "tie_break_weights": [1.0]})
