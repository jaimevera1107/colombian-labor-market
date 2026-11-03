"""Tests of the non-negotiable dual-annex monthly time-matching rule."""
from pathlib import Path

import pytest

from icml.operations.source_pair import check_monthly_sources, expected_social_window


def test_rolling_quarter_crosses_year():
    assert expected_social_window("2026-09") == ("2026-07", "2026-09")
    assert expected_social_window("2027-01") == ("2026-11", "2027-01")


def test_both_sources_missing_block():
    out = check_monthly_sources("2026-09", None, None, "2026-09", "2026-07", "2026-09")
    assert not out["may_run_full_monthly_reconstruction"]
    assert not out["may_publish_new_vintage"]
    assert "MISSING_INFORMALITY_AND_SOCIAL_SECURITY_ANNEX" in out["blockers"]


def test_missing_social_never_passes_even_when_geih_exists(tmp_path):
    geih = tmp_path / "labor.xlsx";geih.write_bytes(b"sample")
    out = check_monthly_sources("2026-09", geih, None, "2026-09", "2026-07", "2026-09")
    assert out["status"].startswith("BLOCKED")
    assert not out["may_run_full_monthly_reconstruction"]


def test_previous_moving_quarter_cannot_replace_target_quarter(tmp_path):
    geih = tmp_path / "labor.xlsx";geih.write_bytes(b"sample")
    social = tmp_path / "social.xlsx";social.write_bytes(b"sample")
    out = check_monthly_sources("2026-09", geih, social, "2026-09", "2026-06", "2026-08")
    assert "SOCIAL_SECURITY_WINDOW_MISMATCH" in out["blockers"]


def test_mismatched_geih_month_blocks(tmp_path):
    geih=tmp_path/'g.xlsx';geih.touch()
    social=tmp_path/'s.xlsx';social.touch()
    out=check_monthly_sources("2026-09",geih,social,"2026-08","2026-07","2026-09")
    assert "GEIH_MONTH_MISMATCH" in out["blockers"]


def test_matching_metadata_is_not_sufficient_for_publication(tmp_path):
    geih=tmp_path/'g.xlsx';geih.touch()
    social=tmp_path/'s.xlsx';social.touch()
    out=check_monthly_sources("2026-09",geih,social,"2026-09","2026-07","2026-09")
    assert out["status"] == "PAIR_CALENDAR_COHERENT_AWAITING_SOURCE_CONTENT_VALIDATION"
    assert not out["content_provenance_verified"]
    assert not out["may_publish_new_vintage"]
    assert not out["may_run_full_monthly_reconstruction"]


def test_invalid_month_rejected():
    with pytest.raises(ValueError):
        check_monthly_sources("2026-13",None,None)
    with pytest.raises(ValueError):
        expected_social_window("2026-00")
