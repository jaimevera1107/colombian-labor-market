"""The 2001-01 splices are adopted: guard the adoption, the version and the status."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

import icml
from icml.recalculation.service import CLEAN_STATUSES, require_clean_recompute, splice_notes
from icml.informality.regime_splice import RegimeSplice
from icml.pipeline.labor_base_splice import LaborBaseSplice
from icml.pipeline.labor_reconstruction import LaborReconstruction

PROJECT = Path(__file__).resolve().parents[2]
CONFIGS = PROJECT / "configs" / "rc1"


def test_the_informality_splice_and_the_labor_reconstruction_are_enabled_in_the_repository_configuration():
    informality = RegimeSplice.from_toml(CONFIGS / "regime_splice.toml")
    labor_base = LaborBaseSplice.from_toml(CONFIGS / "labor_base_splice.toml")
    reconstruction = LaborReconstruction.from_toml(CONFIGS / "labor_reconstruction.toml")
    assert informality.enabled and reconstruction.enabled
    # the PET base splice of 2.3.0 is superseded: the line anchored at the official month closes its seam
    assert not labor_base.enabled
    # one seam, one month: informality and the labor history change at the same place
    assert informality.break_month == reconstruction.splice_month == "2001-01"


def test_the_methodological_change_bumped_the_version_consistently():
    pyproject = tomllib.loads((PROJECT / "pyproject.toml").read_text("utf-8"))["project"]["version"]
    assert icml.__version__ == pyproject
    major, minor = (int(x) for x in re.match(r"(\d+)\.(\d+)", pyproject).groups())
    assert (major, minor) >= (2, 4)
    assert f"## {pyproject}" in (PROJECT / "CHANGELOG.md").read_text("utf-8")


def test_the_methodology_note_exists():
    note = (PROJECT / "docs" / "production" / "EMPALMES_2001.md").read_text("utf-8")
    assert "Para revertir" in note and "2.3.0" in note
    rebuilt = (PROJECT / "docs" / "production" / "RECONSTRUCCION_LABORAL.md").read_text("utf-8")
    assert "Para revertir" in rebuilt and "2.4.0" in rebuilt and "PET" in rebuilt


def test_a_recompute_is_clean_in_either_state():
    require_clean_recompute({"status": "RECOMPUTED_ALL_EIGHT_AUDITED"})
    require_clean_recompute(
        {"status": "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES", "regime_splice": {"enabled": True}}
    )
    require_clean_recompute(
        {"status": "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES", "labor_base_splice": {"enabled": True}}
    )
    require_clean_recompute(
        {"status": "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES", "labor_reconstruction": {"enabled": True}}
    )
    assert len(CLEAN_STATUSES) == 2


@pytest.mark.parametrize(
    "report",
    [
        {"status": "RECOMPUTATION_FAILED_NOT_PUBLISHED"},
        {"status": "RECOMPUTED_BUT_CROSS_AUDIT_FAILED"},
        {"status": "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_NEW_VINTAGE"},  # without a cutoff it is not a new vintage
        {"status": "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_NEW_VINTAGE", "cutoff": "2026-08"},  # the frozen month is not new
        {},
    ],
)
def test_other_states_are_never_clean(report):
    with pytest.raises(RuntimeError, match="did not finish cleanly"):
        require_clean_recompute(report)


def test_a_spliced_status_without_an_enabled_splice_is_refused():
    report = {
        "status": "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_WITH_SPLICES",
        "regime_splice": {"enabled": False},
        "labor_base_splice": {"enabled": False},
        "labor_reconstruction": {"enabled": False},
    }
    with pytest.raises(RuntimeError, match="no splice is enabled"):
        require_clean_recompute(report)


def test_the_manifest_note_describes_only_the_enabled_splices():
    report = {
        "regime_splice": {"enabled": True, "break_month": "2001-01", "window_months": 24},
        "labor_base_splice": {"enabled": True, "break_month": "2001-01", "window_months": 24, "city_break": "pooled"},
    }
    notes = splice_notes(report)
    assert notes["regime_splice"] == "enabled; break_month=2001-01; window_months=24"
    assert notes["labor_base_splice"].endswith("city_break=pooled")
    assert splice_notes({"regime_splice": {"enabled": False}}) == {}


def test_the_manifest_note_describes_the_reconstruction():
    report = {"labor_reconstruction": {"enabled": True, "break_month": "2001-01", "scaling_factor": 0.45}}
    assert splice_notes(report)["labor_reconstruction"] == "enabled; splice_month=2001-01; scaling_factor=0.45"


def test_another_cutoff_is_a_clean_new_vintage():
    require_clean_recompute({"status": "RECOMPUTED_ALL_EIGHT_CROSS_AUDITED_NEW_VINTAGE", "cutoff": "2026-07"})
