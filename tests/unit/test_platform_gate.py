"""The reference comparison is strict on the reference platform and bounded on another one."""

from __future__ import annotations

import json

import pytest

from icml.operations import integral


def _equivalent():
    return {"status": "EQUIVALENT_WITHIN_TOLERANCES", "issues": [], "maximum_relative_difference": 0.0}


def _numeric(rel):
    return {"status": "MISMATCH", "issues": ["numeric_tolerance_exceeded"], "missing_keys": [], "new_keys": [],
            "old_only_columns": [], "candidate_only_columns": [], "maximum_relative_difference": rel}


def test_bounded_numeric_mismatches_are_accepted_and_measured():
    results = {p: _equivalent() for p in integral.SELECTED_IDS}
    results["labor.departamentos"] = _numeric(0.031)
    results["labor.nacionales"] = _numeric(0.004)
    verdict = integral._platform_dependent_mismatch(results)
    assert verdict["accepted"] and verdict["max_relative_difference"] == pytest.approx(0.031) and verdict["blocking"] == []


def test_a_difference_above_the_bound_or_a_structural_one_still_blocks():
    results = {p: _equivalent() for p in integral.SELECTED_IDS}
    results["labor.departamentos"] = _numeric(integral.PLATFORM_RELATIVE_BOUND + 0.01)
    assert not integral._platform_dependent_mismatch(results)["accepted"]
    results = {p: _equivalent() for p in integral.SELECTED_IDS}
    results["informalidad.ciudades"] = {**_numeric(0.001), "issues": ["numeric_tolerance_exceeded", "categorical_drift"]}
    assert integral._platform_dependent_mismatch(results)["blocking"] == ["informalidad.ciudades"]
    results = {p: _equivalent() for p in integral.SELECTED_IDS}
    results["labor.ciudades"] = {**_numeric(0.001), "missing_keys": [["05", "2026-08"]]}
    assert not integral._platform_dependent_mismatch(results)["accepted"]


def test_platform_differs_looks_at_system_and_machine_only(tmp_path):
    now = integral.current_platform()
    assert not integral.platform_differs(None)
    assert not integral.platform_differs({"system": now["system"], "machine": now["machine"], "python": "0.0", "xgboost": "0"})
    assert integral.platform_differs({"system": "Windows" if now["system"] != "Windows" else "Linux", "machine": now["machine"]})
    (tmp_path / "datos/2_procesamiento/productos_congelados").mkdir(parents=True)
    record = integral.write_reference_platform(tmp_path)
    assert integral.read_reference_platform(tmp_path) == record
    assert json.loads((tmp_path / integral.REFERENCE_PLATFORM_FILE).read_text())["system"] == now["system"]


def test_the_repository_records_the_platform_of_the_frozen_reference():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    record = integral.read_reference_platform(root)
    assert record is not None and {"system", "machine", "python", "xgboost"} <= set(record)
