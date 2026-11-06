"""Characterization of the RC1 reference: the migration's fixed point."""

import pytest

from icml.domain.contracts import (
    IdentityPolicy,
    check_identities_by_provenance,
)
from icml.domain.periods import validate_periods
from icml.domain.provenance import resolve_legacy_labels
from icml.domain.quantities import to_canonical_columns
from icml.domain.territories import load_urban_domains, territory_codes
from icml.regression.compare import compare_tables
from icml.regression.golden import check_integrity, load_golden_table

pytestmark = pytest.mark.golden
# RC1 contract: published GEIH figures may carry rounding residuals; RC1
# accepts up to two persons (``quality_official`` in the legacy
# fases/01_nacional/src/icml/nacional.py). Estimated values must close to
# numerical precision.
RC1_IDENTITY_POLICY = IdentityPolicy(
    observed_tolerance_persons=2.0,
    estimated_tolerance_persons=1e-6,
)
PROVENANCE_COLUMNS = {
    "product.national": "origin",
    "product.departmental": "origen",
    "product.urban_signals": "origin",
}


def test_catalog_is_complete_and_consistent(catalog):
    roles = {a.role for a in catalog.artifacts}
    assert {"source", "stage_output", "final_product"} <= set(roles)
    assert len(catalog.by_stage("reconciliation.pet_linearization")) == 2


def test_golden_hashes_match_catalog(catalog, golden_dir):
    assert check_integrity(golden_dir, catalog) == ()


def test_comparator_accepts_every_golden_table_against_itself(
    catalog, golden_dir
):
    for artifact in catalog.artifacts:
        if not artifact.is_tabular:
            continue
        table = load_golden_table(golden_dir, artifact)
        report = compare_tables(
            table,
            table.copy(),
            artifact_id=artifact.artifact_id,
            keys=artifact.keys,
        )
        assert report.passed, artifact.artifact_id


@pytest.mark.parametrize(
    ("artifact_id", "unit_column", "expected_units"),
    [
        ("product.national", None, 1),
        ("product.departmental", "dep_code", 33),
        ("product.urban_signals", "city_code", 33),
    ],
)
def test_final_products_cover_404_months(
    catalog, golden_dir, artifact_id, unit_column, expected_units
):
    table = load_golden_table(golden_dir, catalog.get(artifact_id))
    groups = (
        [table]
        if unit_column is None
        else [group for _, group in table.groupby(unit_column)]
    )
    assert len(groups) == expected_units
    for group in groups:
        periods = validate_periods(group["periodo"].sort_values())
        assert len(periods) == 404


@pytest.mark.parametrize("artifact_id", sorted(PROVENANCE_COLUMNS))
def test_final_products_satisfy_identities(catalog, golden_dir, artifact_id):
    table = load_golden_table(golden_dir, catalog.get(artifact_id))
    reports = check_identities_by_provenance(
        to_canonical_columns(table),
        provenance_column=PROVENANCE_COLUMNS[artifact_id],
        policy=RC1_IDENTITY_POLICY,
    )
    failed = {c: r for c, r in reports.items() if not r.passed}
    assert not failed, failed


def test_reference_catalogs_match_rc1_units(catalog, golden_dir):
    departmental = load_golden_table(
        golden_dir, catalog.get("product.departmental")
    )
    urban = load_golden_table(golden_dir, catalog.get("product.urban_signals"))
    assert set(departmental["dep_code"]) == set(territory_codes())
    assert set(urban["city_code"]) == {
        d.dane_code for d in load_urban_domains()
    }


def test_every_rc1_provenance_label_is_registered(catalog, golden_dir):
    labels: set[str] = set()
    for artifact_id, column in PROVENANCE_COLUMNS.items():
        table = load_golden_table(golden_dir, catalog.get(artifact_id))
        labels |= set(table[column].astype(str))
    resolve_legacy_labels(labels)
