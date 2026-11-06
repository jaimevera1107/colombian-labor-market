"""Contract of the candidate representativeness-factor products."""

import numpy as np
import pytest

from icml.departmental.pipeline import OUTPUTS as DEPARTMENTAL_OUTPUTS
from icml.integration.pipeline import OUTPUTS as INTEGRATION_OUTPUTS
from icml.reconciliation.pipeline import OUTPUTS

pytestmark = pytest.mark.golden

PARTIAL = (81, 85, 86, 88, 91, 94, 95, 97, 99)
QUANTITIES = ("employed", "unemployed", "inactive", "population")
# First month with observed GEIH national coverage (earlier months are
# reconstructed in full) and the month DANE incorporated the capitals.
RECONCILE_FROM = "2001-01"
CAPITALS_ENTRY = "2014-01"


@pytest.fixture(scope="module")
def products(full_chain):
    stores = full_chain["stores"]
    factors = stores["reconciliation"].read(OUTPUTS["departmental_factors"])
    national = stores["integration"].read(
        INTEGRATION_OUTPUTS["national_monthly"]
    )
    anchors = stores["departmental"].read(
        DEPARTMENTAL_OUTPUTS["official_anchors"]
    )
    return factors, national, anchors


def test_full_territories_have_factor_one(products):
    factors, _, _ = products
    scope = (factors["period"] >= "2001-01") & ~factors["dep_code"].isin(
        PARTIAL
    )
    for quantity in QUANTITIES:
        np.testing.assert_allclose(
            factors.loc[scope, f"factor_{quantity}"], 1.0, atol=1e-12
        )


def test_partial_territories_enter_national_from_2014(products):
    """Factor rule documented in ``reconciliation.representativeness``.

    1993-2000 has no observed GEIH national coverage and is reconstructed
    in full, so every factor is 1. From 2001 until DANE incorporated the
    capitals (2014-01) their GEIH coverage factor is 0. From 2014 on it
    is a proportion in ``[0, 1]``.
    """
    factors, _, _ = products
    partial = factors["dep_code"].isin(PARTIAL)
    full_reconstruction = partial & (factors["period"] < RECONCILE_FROM)
    before_entry = (
        partial
        & (factors["period"] >= RECONCILE_FROM)
        & (factors["period"] < CAPITALS_ENTRY)
    )
    after_entry = partial & (factors["period"] >= CAPITALS_ENTRY)
    # Guard against vacuous passes if a period range ever becomes empty.
    assert full_reconstruction.any()
    assert before_entry.any()
    assert after_entry.any()
    np.testing.assert_array_equal(
        factors.loc[full_reconstruction, "factor_population"], 1.0
    )
    np.testing.assert_array_equal(
        factors.loc[before_entry, "factor_population"], 0.0
    )
    assert factors.loc[after_entry, "factor_population"].between(0, 1).all()


def test_weighted_sum_equals_dane_national(products):
    factors, national, _ = products
    reference = national.set_index("period")
    scope = factors[factors["period"] >= "2001-01"]
    for quantity in QUANTITIES:
        weighted = (
            (scope[quantity] * scope[f"factor_{quantity}"])
            .groupby(scope["period"])
            .sum()
        )
        target = reference.loc[weighted.index, quantity]
        assert float((weighted / target - 1).abs().max()) < 1e-6, quantity


# With the proportional rule, anchors absorb their share of the sources'
# non-additivity. These are the measured bounds (docs/evaluation/05).
ANCHOR_BOUNDS = {
    "employed": 1.0,
    "unemployed": 1.9,
    "inactive": 1.7,
    "population": 0.2,
}
# Headline deviation from official figures, over every territory and
# year including Bogotá, the capitals and the provisional 2026 months
# (docs/evaluation/06_OFFICIAL_DEVIATION.md).
DEVIATION_BOUNDS = {
    "employed": 1.3,
    "unemployed": 1.9,
    "inactive": 1.7,
    "population": 0.4,
}


def test_anchors_stay_within_the_declared_bounds(products):
    factors, _, anchors = products
    window = factors[
        factors["dep_code"].isin(anchors["dep_code"])
        & factors["year"].between(2007, 2025)
    ]
    means = window.groupby(["dep_code", "year"])[list(QUANTITIES)].mean()
    official = anchors.set_index(["dep_code", "year"])
    for quantity, bound in ANCHOR_BOUNDS.items():
        deviation = (
            100 * (means[quantity] / official.loc[means.index, quantity] - 1)
        ).abs()
        assert float(deviation.max()) <= bound, quantity


def test_residual_share_explains_the_anchor_deviation(products):
    factors, _, anchors = products
    scope = factors[
        (factors["period"] >= "2001-01")
        & factors["dep_code"].isin(anchors["dep_code"])
    ]
    for quantity in QUANTITIES:
        reconstructed = (
            scope[f"{quantity}_represented"]
            - scope[f"{quantity}_residual_share"]
        )
        assert (reconstructed > 0).all(), quantity


def test_icml_national_exceeds_dane_by_coverage(full_chain):
    national = full_chain["stores"]["reconciliation"].read(
        OUTPUTS["national_icml"]
    )
    scope = national[national["period"] >= "2001-01"]
    assert scope["coverage_gap_population_pct"].between(1.5, 3.5).all()


def test_official_deviation_covers_every_published_figure(full_chain):
    """The headline accuracy table is complete and consistent."""
    store = full_chain["stores"]["reconciliation"]
    deviation = store.read(OUTPUTS["official_deviation"])
    assert set(deviation["quantity"]) == set(QUANTITIES)
    assert set(deviation["reference_type"]) == {
        "ancla_anual_departamental",
        "geih_capital_ventanas",
        "geih_dominio_urbano",
    }
    reconstructed = deviation["official"] * (
        1 + deviation["deviation_pct"] / 100
    )
    assert float((reconstructed - deviation["published"]).abs().max()) < 1e-6
    for quantity, bound in DEVIATION_BOUNDS.items():
        rows = deviation[deviation["quantity"] == quantity]
        assert float(rows["deviation_pct"].abs().max()) <= bound, quantity
