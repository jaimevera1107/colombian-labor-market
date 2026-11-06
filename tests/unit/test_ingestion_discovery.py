"""Annex discovery: the name classifies, the content decides."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from icml.ingestion.discovery import (
    AmbiguousAnnexError,
    annex_for,
    classify,
    detect_cutoff,
    discover,
    parse_period,
)
from icml.ingestion.validation import AnnexPeriodMismatch, verify_annex
from tests.annexes import annex as annex_path

PROJECT = Path(__file__).resolve().parents[2]
INGESTA = PROJECT / "datos" / "1_ingesta"
CONFIGS = PROJECT / "configs" / "rc1"
JULY = annex_path("mercado_laboral", "2026-07")
INF_JULY = annex_path("informalidad", "2026-07")
real = pytest.mark.skipif(not (JULY.is_file() and INF_JULY.is_file()), reason="annexes not present")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("geih_mercado_laboral_2026-09.xlsx", ("mercado_laboral", "2026-09")),
        ("GEIH_Mercado_Laboral_2026-09.XLSX", ("mercado_laboral", "2026-09")),
        ("Anexo GEIH Septiembre 2026.xlsx", ("mercado_laboral", "2026-09")),
        ("Anexo_GEIH_Agosto_2026.xlsx", ("mercado_laboral", "2026-08")),
        ("anex-GEIH-sep2026.xlsx", ("mercado_laboral", "2026-09")),
        ("anex-GEIH-sept2026.xlsx", ("mercado_laboral", "2026-09")),
        ("geih_informalidad_2026-09.xlsx", ("informalidad", "2026-09")),
        ("Anexo GEIH Informalidad Septiembre 2025.xlsx", ("informalidad", "2025-09")),
        ("Anexo GEIH Informalidad Marzo 2021.xls", ("informalidad", "2021-03")),
        ("geih_departamentos_2026.xlsx", ("departamentos", "2026")),
        ("Anexo GEIH Departamentos 2025.xlsx", ("departamentos", "2025")),
        ("Anexo GEIH Diciembre 2025.xlsx", ("mercado_laboral", "2025-12")),
    ],
)
def test_names_in_any_style_are_classified(name, expected):
    assert classify(name) == expected


@pytest.mark.parametrize("name", ["Salarios.xlsx", "PIB Departamentos 2024.xlsx", "notas.xlsx", "geih_sin_fecha.xlsx"])
def test_files_that_are_not_annexes_are_ignored(name):
    assert classify(name) is None


def test_parse_period_rejects_impossible_months():
    assert parse_period("geih_2026-13.xlsx") is None
    assert parse_period("geih_2026-12.xlsx") == "2026-12"


def _touch(root: Path, name: str, content: bytes = b"x") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_cutoff_is_the_last_month_with_both_annexes(tmp_path):
    for month in ("07", "08", "09"):
        _touch(tmp_path, f"a/geih_mercado_laboral_2026-{month}.xlsx", month.encode())
    for month in ("07", "08"):
        _touch(tmp_path, f"b/Anexo GEIH Informalidad {'Julio' if month == '07' else 'Agosto'} 2026.xlsx", month.encode())
    result = detect_cutoff(tmp_path)
    assert result["cutoff"] == "2026-08"  # September has only the labor annex
    assert result["latest_mercado_laboral"] == "2026-09"
    assert result["latest_informalidad"] == "2026-08"
    assert result["pending"]["only_mercado_laboral"] == ["2026-09"]
    assert result["pending"]["only_informalidad"] == []


def test_without_a_pair_there_is_no_cutoff(tmp_path):
    _touch(tmp_path, "geih_mercado_laboral_2026-09.xlsx")
    assert detect_cutoff(tmp_path)["cutoff"] is None


def test_identical_copies_are_one_annex_and_different_files_are_ambiguous(tmp_path):
    _touch(tmp_path, "x/Anexo GEIH Agosto 2026.xlsx", b"same")
    _touch(tmp_path, "y/geih_mercado_laboral_2026-08.xlsx", b"same")
    assert len(discover(tmp_path)["mercado_laboral"]) == 1
    _touch(tmp_path, "z/anex-GEIH-ago2026.xlsx", b"different")
    with pytest.raises(AmbiguousAnnexError, match="2026-08"):
        discover(tmp_path)


def test_binary_xls_archives_never_decide_the_cutoff(tmp_path):
    _touch(tmp_path, "Anexo GEIH Informalidad Marzo 2026.xls", b"old")
    _touch(tmp_path, "geih_mercado_laboral_2026-03.xlsx", b"new")
    assert detect_cutoff(tmp_path)["cutoff"] is None


def test_annex_for_returns_the_requested_month(tmp_path):
    path = _touch(tmp_path, "Anexo GEIH Julio 2026.xlsx")
    assert annex_for(tmp_path, "mercado_laboral", "2026-07").path == path
    with pytest.raises(FileNotFoundError):
        annex_for(tmp_path, "mercado_laboral", "2026-08")


@real
def test_real_folder_supports_the_august_cutoff():
    result = detect_cutoff(INGESTA)
    assert result["cutoff"] == "2026-08"
    assert result["pending"] == {"only_mercado_laboral": [], "only_informalidad": []}


@real
def test_content_decides_the_period_and_a_misnamed_file_is_caught(tmp_path):
    labor = annex_for(INGESTA, "mercado_laboral", "2026-07")
    assert verify_annex(labor, CONFIGS)["declared"] == "2026-07"
    informality = annex_for(INGESTA, "informalidad", "2026-07")
    assert verify_annex(informality, CONFIGS)["declared"] == "2026-07"
    # The July workbook dropped in under a September name must be refused.
    wrong = tmp_path / "geih_mercado_laboral_2026-09.xlsx"
    shutil.copy2(JULY, wrong)
    misnamed = annex_for(tmp_path, "mercado_laboral", "2026-09")
    with pytest.raises(AnnexPeriodMismatch, match="declares 2026-07"):
        verify_annex(misnamed, CONFIGS)


def test_office_lock_files_and_hidden_files_are_never_annexes(tmp_path):
    _touch(tmp_path, "geih_mercado_laboral_2026-08.xlsx", b"real")
    _touch(tmp_path, "~$geih_mercado_laboral_2026-08.xlsx", b"lock")  # Excel open on Windows
    _touch(tmp_path, ".geih_informalidad_2026-08.xlsx", b"hidden")
    _touch(tmp_path, "LEEME.md", b"notes")
    found = discover(tmp_path)
    assert [a.path.name for a in found["mercado_laboral"]] == ["geih_mercado_laboral_2026-08.xlsx"]
    assert found["informalidad"] == []
    assert classify("~$Anexo GEIH Agosto 2026.xlsx") is None
