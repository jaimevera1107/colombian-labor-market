"""Vintage comparison (synthetic) and annex checks (real annexes, if present)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from icml.recalculation.policy import AnchorPolicy
from icml.recalculation.replay import compare_labor_vintages
from tests.annexes import annex

POLICY = AnchorPolicy(2025)
PROJECT = Path(__file__).resolve().parents[2]
CONFIGS = PROJECT / "configs" / "rc1"
JULY = annex("mercado_laboral", "2026-07")
AUGUST = annex("mercado_laboral", "2026-08")
PROXIES_AUGUST = PROJECT / "datos/2_procesamiento/fuentes_preparadas/urbano/proxies_anuales_ventanas_2026_08.csv"
needs_annexes = pytest.mark.skipif(
    not (JULY.is_file() and AUGUST.is_file()), reason="DANE annexes not present"
)


def _products(folder: Path, periods: list[str], shift: float) -> None:
    folder.mkdir(parents=True)
    frames = {
        "ciudades": ("city_code", ["05", "08"]),
        "departamentos": ("dep_code", ["05", "08"]),
        "nacionales": ("national_type", ["DANE_REFERENCIA", "ICML_COMPLETO"]),
    }
    for name, (key, codes) in frames.items():
        rows = [
            {"period": p, key: c, "employed": 100.0 + (p >= "2021-01") * shift}
            for p in periods
            for c in codes
        ]
        pd.DataFrame(rows).to_csv(folder / f"{name}.csv", index=False)


def test_naive_recomputation_would_change_frozen_years_and_graft_prevents_it(tmp_path):
    previous = ["2020-12", "2021-01", "2025-12", "2026-01"]
    current = [*previous, "2026-02"]
    _products(tmp_path / "jul", previous, 0.0)
    _products(tmp_path / "aug", current, 3.0)
    report = compare_labor_vintages(tmp_path / "jul", tmp_path / "aug", POLICY)
    cities = report["products"]["ciudades"]
    # Only 2021 and 2025 are re-identified (2 cities each); 2020 is not.
    assert cities["by_year"] == {2021: 2, 2025: 2}
    assert cities["frozen_cells_a_naive_recomputation_would_change"] == 4
    assert cities["frozen_cells_changed_after_graft"] == 0
    assert cities["new_rows"] == 2
    assert cities["frozen_rows_kept_from_previous"] == 6
    assert cities["open_rows_taken_from_current"] == 4  # 2026-01 and 2026-02 x 2 cities


@needs_annexes
def test_window_proxies_follow_the_cutoff_and_reject_incompatible_sources():
    from icml.operations.excel_historical_sources import extract_window_proxies

    august = pd.DataFrame(extract_window_proxies(AUGUST, "2026-08"))
    current = pd.read_csv(PROXIES_AUGUST)
    merged = august.astype({"dep_code": int, "year": int}).merge(
        current, on=["dep_code", "year"], suffixes=("_new", "_old")
    )
    assert len(august) == 192 == len(merged)
    for column in ("employed", "inactive", "pea", "pet", "population", "unemployed"):
        assert (merged[f"{column}_new"] - merged[f"{column}_old"]).abs().max() < 1e-6
    assert len(extract_window_proxies(JULY, "2026-07")) == 192
    with pytest.raises(ValueError, match="moving-year"):
        extract_window_proxies(JULY, "2026-08")  # July annex lacks August windows
    with pytest.raises(ValueError, match="2022"):
        extract_window_proxies(JULY, "2021-12")


@needs_annexes
def test_july_to_august_annexes_have_no_revisions_on_real_figures():
    from icml.recalculation.annex_checks import compare_annex_releases

    report = compare_annex_releases(
        JULY,
        AUGUST,
        national_config=CONFIGS / "national.toml",
        integration_config=CONFIGS / "integration.toml",
        previous_windows=56,
        current_windows=57,
        policy=POLICY,
    )
    assert report["status"] == "PASS"
    national = report["sources"]["national_monthly"]
    windows = report["sources"]["city_windows"]
    assert national["observations_compared"] == {"previous": 1842, "current": 1848}
    assert windows["observations_compared"] == {"previous": 10752, "current": 10944}
    assert national["n_revisions"] == windows["n_revisions"] == 0
    assert national["open_year_revisions"] == windows["open_year_revisions"] == 0


@needs_annexes
def test_gate_catches_a_revised_real_figure():
    from icml.recalculation.annex_checks import national_observations
    from icml.recalculation.gates import check_frozen_observations

    previous = national_observations(JULY, CONFIGS / "national.toml")
    current = previous.copy()
    row = current.index[(current["period"] == "2024-05") & (current["quantity"] == "employed")][0]
    current.loc[row, "value"] += 1000.0
    report = check_frozen_observations(
        previous, current, POLICY, keys=["period", "quantity"], value="value"
    )
    assert report["status"] == "BLOCKED"
    assert report["n_revisions"] == 1
    # The same change in an open year is not a block.
    open_row = current.index[(current["period"] == "2026-01") & (current["quantity"] == "employed")][0]
    clean = previous.copy()
    clean.loc[open_row, "value"] += 1000.0
    assert check_frozen_observations(
        previous, clean, POLICY, keys=["period", "quantity"], value="value"
    )["status"] == "PASS"


INF_JULY = annex("informalidad", "2026-07")
INF_APRIL = annex("informalidad", "2026-04")
INF_MAY_2025 = annex("informalidad", "2025-05")
INF_AUGUST = annex("informalidad", "2026-08")
needs_informality = pytest.mark.skipif(
    not all(p.is_file() for p in (INF_JULY, INF_APRIL, INF_MAY_2025, INF_AUGUST)),
    reason="informality annexes not present",
)


def _national_total_row(annex: Path, row: int) -> list:
    cells = pd.read_excel(annex, sheet_name="Total nacional", header=None, nrows=45)
    return cells.astype(object).where(cells.notna(), None).values.tolist()[row][1:]


@needs_informality
def test_informality_july_to_august_has_no_changes_on_real_figures():
    from icml.recalculation.annex_checks import compare_informality_releases

    report = compare_informality_releases(INF_JULY, INF_AUGUST, POLICY)
    assert report["status"] == "PASS"
    # 28 series (25 city blocks + 3 national) x 3 measures x windows.
    assert report["observations_compared"] == {"previous": 5460, "current": 5544}
    assert report["n_revisions"] == 0
    assert report["n_frozen_observations_removed"] == 0
    assert report["n_added_in_frozen_years"] == 0
    assert report["open_year_revisions"] == 0


@needs_informality
def test_an_annex_published_with_a_hole_is_rejected_and_the_hole_is_later_filled():
    from icml.informality.extract_annexes import extract_new

    # April-June 2026 carry an empty national window (Dec 2022 - Feb 2023,
    # position 23); the extractor refuses it instead of imputing a value.
    april = _national_total_row(INF_APRIL, 13)
    assert april[23] is None
    assert all(v is not None for v in april[:23])
    assert _national_total_row(INF_AUGUST, 13)[23] == pytest.approx(22064.135597)

    def matrix(annex: Path, sheet: str, rows: int) -> list:
        cells = pd.read_excel(annex, sheet_name=sheet, header=None, nrows=rows)
        return cells.astype(object).where(cells.notna(), None).values.tolist()

    with pytest.raises(ValueError, match="Cobertura nacional insuficiente"):
        extract_new(matrix(INF_APRIL, "Ciudades", 120), matrix(INF_APRIL, "Total nacional", 45))


@needs_informality
def test_a_release_that_predates_a_frozen_year_is_blocked_by_added_windows():
    from icml.recalculation.annex_checks import compare_informality_releases

    # May 2025 has no windows after May 2025: Jun-Dec 2025 are 7 windows in a
    # year that is now frozen, for 28 series x 3 measures.
    report = compare_informality_releases(INF_MAY_2025, INF_AUGUST, POLICY)
    assert report["status"] == "BLOCKED"
    assert report["n_added_in_frozen_years"] == 28 * 3 * 7
    assert report["n_revisions"] == 0
