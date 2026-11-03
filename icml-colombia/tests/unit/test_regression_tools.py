import hashlib

import numpy as np
import pandas as pd
import pytest

from icml.cli import main
from icml.regression.catalog import load_catalog
from icml.regression.compare import Tolerance, compare_tables
from icml.regression.golden import (
    capture_golden,
    check_integrity,
    load_golden_table,
)


@pytest.fixture
def reference():
    return pd.DataFrame(
        {
            "dep_code": [5, 5, 8],
            "periodo": ["2000-01", "2000-02", "2000-01"],
            "employed": [10.0, 11.0, np.nan],
            "origen": ["a", "a", "b"],
        }
    )


def test_identical_tables_pass(reference):
    report = compare_tables(
        reference,
        reference.copy(),
        artifact_id="x.y",
        keys=("dep_code", "periodo"),
    )
    assert report.passed


def test_difference_within_tolerance_passes(reference):
    candidate = reference.copy()
    candidate.loc[0, "employed"] += 5e-7
    assert compare_tables(reference, candidate, artifact_id="x.y").passed


def test_difference_above_tolerance_fails(reference):
    candidate = reference.copy()
    candidate.loc[0, "employed"] += 1e-5
    report = compare_tables(reference, candidate, artifact_id="x.y")
    assert not report.passed
    assert report.numeric[1].max_abs_diff == pytest.approx(1e-5)


def test_relative_tolerance_override(reference):
    candidate = reference.copy()
    candidate.loc[0, "employed"] += 1e-3
    report = compare_tables(
        reference,
        candidate,
        artifact_id="x.y",
        column_tolerances={"employed": Tolerance(0.0, 1e-3)},
    )
    assert report.passed


def test_row_order_is_irrelevant_with_keys(reference):
    shuffled = reference.iloc[::-1]
    assert compare_tables(
        reference, shuffled, artifact_id="x.y", keys=("dep_code", "periodo")
    ).passed


def test_missing_and_extra_keys_reported(reference):
    candidate = reference.copy()
    candidate.loc[2, "periodo"] = "2000-03"
    report = compare_tables(
        reference, candidate, artifact_id="x.y", keys=("dep_code", "periodo")
    )
    assert (report.n_missing_keys, report.n_extra_keys) == (1, 1)
    assert not report.passed


def test_nan_mismatch_and_text_mismatch(reference):
    candidate = reference.copy()
    candidate.loc[2, "employed"] = 0.0
    candidate.loc[0, "origen"] = "z"
    report = compare_tables(reference, candidate, artifact_id="x.y")
    assert report.text_mismatches["origen"] == 1
    assert any(d.n_missing_mismatch == 1 for d in report.numeric)


def test_schema_differences_and_column_map(reference):
    candidate = reference.rename(columns={"employed": "ocupados"})
    assert not compare_tables(reference, candidate, artifact_id="x.y").passed
    assert compare_tables(
        reference,
        candidate,
        artifact_id="x.y",
        column_map={"ocupados": "employed"},
    ).passed


def test_row_count_mismatch_without_keys(reference):
    report = compare_tables(reference, reference.iloc[:2], artifact_id="x.y")
    assert not report.passed


def _write_catalog(tmp_path, files):
    lines = ["schema_version = 1", 'reference = "test"', ""]
    for artifact_id, rel, content in files:
        path = tmp_path / "legacy" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        lines += [
            "[[artifact]]",
            f'id = "{artifact_id}"',
            'stage = "s"',
            'role = "stage_output"',
            f'legacy_path = "{rel}"',
            "keys = []",
            f'sha256 = "{digest}"',
            "",
        ]
    catalog = tmp_path / "catalog.toml"
    catalog.write_text("\n".join(lines), encoding="utf-8")
    return catalog


def test_capture_verify_and_load(tmp_path):
    catalog_path = _write_catalog(
        tmp_path,
        [("a.table", "x/t.csv", b"c\n1\n"), ("a.blob", "y/b.json", b"{}")],
    )
    catalog = load_catalog(catalog_path)
    golden = tmp_path / "golden"
    capture_golden(tmp_path / "legacy", catalog, golden)
    assert check_integrity(golden, catalog) == ()
    table = load_golden_table(golden, catalog.get("a.table"))
    assert table["c"].tolist() == [1]
    with pytest.raises(ValueError):
        load_golden_table(golden, catalog.get("a.blob"))
    with pytest.raises(FileExistsError):
        capture_golden(tmp_path / "legacy", catalog, golden)


def test_capture_rejects_tampered_legacy_tree(tmp_path):
    catalog_path = _write_catalog(tmp_path, [("a.table", "t.csv", b"c\n1\n")])
    (tmp_path / "legacy" / "t.csv").write_bytes(b"c\n2\n")
    with pytest.raises(RuntimeError, match="sha256 mismatch"):
        capture_golden(
            tmp_path / "legacy",
            load_catalog(catalog_path),
            tmp_path / "golden",
        )


def test_catalog_rejects_duplicates_and_bad_schema(tmp_path):
    catalog_path = _write_catalog(
        tmp_path, [("a.t", "t.csv", b"x"), ("a.t", "u.csv", b"y")]
    )
    with pytest.raises(ValueError, match="Duplicated"):
        load_catalog(catalog_path)
    bad = tmp_path / "bad.toml"
    bad.write_text('schema_version = 9\nreference = "x"\n')
    with pytest.raises(ValueError, match="schema"):
        load_catalog(bad)


def test_cli_verify_exit_codes(tmp_path):
    catalog_path = _write_catalog(tmp_path, [("a.t", "t.csv", b"c\n1\n")])
    args = [
        "golden",
        "verify",
        "--root",
        str(tmp_path / "legacy"),
        "--catalog",
        str(catalog_path),
    ]
    assert main(args) == 0
    (tmp_path / "legacy" / "t.csv").write_bytes(b"tampered")
    assert main(args) == 2
