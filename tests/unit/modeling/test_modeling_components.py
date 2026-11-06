import numpy as np
import pandas as pd
import pytest

from icml.modeling.folds import FoldPolicy, make_folds
from icml.modeling.selection import RateCloser, causal_transform
from icml.modeling.training import coherent_rates


def test_coherent_rates_satisfy_identity():
    raw = {
        "to": np.array([0.5, 0.9]),
        "td": np.array([0.1, 0.3]),
        "tgp": np.array([0.6, 0.2]),
        "pet_demog": np.array([0.7, 1.4]),
    }
    rates = coherent_rates(raw)
    np.testing.assert_allclose(rates["to"], rates["tgp"] * (1 - rates["td"]))
    assert rates["pet_demog"].max() <= 1


@pytest.mark.parametrize(
    "variant", ["legacy", "balanced", "td_priority", "tgp_priority"]
)
def test_rate_closer_variants_close_identity(variant):
    raw = np.array([[0.55, 0.12, 0.66, 0.7], [0.4, 0.2, 0.6, 0.65]])
    closed = RateCloser(55).close(raw, variant)
    np.testing.assert_allclose(
        closed[:, 0], closed[:, 2] * (1 - closed[:, 1]), atol=1e-12
    )


def test_rate_closer_rejects_unknown_variant():
    with pytest.raises(ValueError):
        RateCloser(5).close(np.ones((1, 4)) * 0.5, "nope")


def test_causal_transform_keeps_first_month_and_large_jumps():
    values = np.array([[0.5], [0.51], [0.7], [0.71]])
    smoothed = causal_transform(values, alpha=0.5, cap=None, large_jump=0.06)
    assert smoothed[0, 0] == 0.5
    assert smoothed[1, 0] == pytest.approx(0.505)
    assert smoothed[2, 0] == pytest.approx(0.7)
    capped = causal_transform(values, alpha=None, cap=0.05, large_jump=0.06)
    assert capped[2, 0] == pytest.approx(0.56)


def _targets():
    rows = []
    for code in range(1, 13):
        for year in range(2007, 2026):
            for month in range(1, 13):
                rows.append(
                    {
                        "dep_code": code,
                        "year": year,
                        "period": f"{year}-{month:02d}",
                        "eligible_training": True,
                    }
                )
    return pd.DataFrame(rows)


def test_folds_have_no_territorial_or_temporal_leakage():
    policy = FoldPolicy(
        n_groups=3, windows=[[2016, 2019], [2019, 2022]], embargo_years=1
    )
    folds = make_folds(
        _targets(), policy, seed=7, first_year=2007, synthetic_code=12
    )
    assert len(folds) == 6
    for fold in folds:
        assert set(fold["training_codes"]).isdisjoint(fold["test_codes"])
        assert 12 not in fold["training_codes"] + fold["test_codes"]
        assert fold["train_year_max"] < fold["test_year_min"] - 1


def test_folds_are_reproducible():
    policy = FoldPolicy(n_groups=3, windows=[[2016, 2019]], embargo_years=1)
    first = make_folds(_targets(), policy, 7, 2007, 12)
    second = make_folds(_targets(), policy, 7, 2007, 12)
    assert first == second
