"""End-to-end orchestration of anchored and total recalculation (fake runner)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from icml.delivery.builder import read_text_table
from icml.recalculation.runner import PRODUCT_KEYS, recalculate
from tests.unit.test_delivery import EXPECTED_COLUMNS, _synthetic

T0 = datetime(2026, 11, 2, 21, 0, 0, tzinfo=UTC)
FROZEN_MONTH, OPEN_MONTH = "2025-12", "2026-01"


def _vintage(shift: float) -> dict[str, pd.DataFrame]:
    """Small products with one frozen and one open month; numbers + shift."""
    frames = {}
    for product in EXPECTED_COLUMNS:
        frame = _synthetic(product).drop_duplicates(list(PRODUCT_KEYS[product]))
        frame = frame.copy()
        frame["period"] = frame["period"].map({"2026-07": FROZEN_MONTH, "2026-08": OPEN_MONTH})
        frame = frame.dropna(subset=["period"])
        for column in frame.columns:
            if column in PRODUCT_KEYS[product] or column in ("territory_name", "city_name"):
                continue
            numbers = pd.to_numeric(frame[column], errors="coerce")
            if numbers.notna().all():
                frame[column] = (numbers + shift).map(repr)
        frames[product] = frame.drop_duplicates(list(PRODUCT_KEYS[product]))
    return frames


def _runner(shift: float):
    def run(staging: Path) -> dict[str, Path]:
        out = {}
        for product, frame in _vintage(shift).items():
            path = staging / f"{product}.csv"
            frame.to_csv(path, index=False)
            out[product] = path
        return out

    return run


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "datos/1_ingesta").mkdir(parents=True)
    (tmp_path / "datos/2_procesamiento/parametros_congelados").mkdir(parents=True)
    (tmp_path / "datos/1_ingesta/geih_agosto.xlsx").write_bytes(b"geih-aug")
    (tmp_path / "datos/2_procesamiento/parametros_congelados/priors.csv").write_text("p")
    return tmp_path


def _go(root, mode="anchored", step=0, shift=0.0, **kw):
    return recalculate(
        root,
        mode,
        anchor_year=2025,
        runner=_runner(shift),
        now=T0 + timedelta(minutes=step),
        check_shapes=False,
        **{"require_annexes": False, "verify_content": False, **kw},
    )


def _delivered(root: Path, result: dict, product: str, universe: str) -> pd.DataFrame:
    folder = root / "datos/3_salida" / result["manifest"]["run_id"]
    entry = next(
        e for e in result["manifest"]["outputs"]
        if e["source_product"] == product and e["universe"] == universe
        and e["path"].endswith(".csv")
    )
    return read_text_table(folder / entry["path"])


def test_first_delivery_is_written_and_promoted(root):
    result = _go(root)
    assert result["plan"]["status"] == "RUN"
    run_id = result["manifest"]["run_id"]
    assert run_id.endswith("_cutoff-2026-08_anchored")
    vigente = json.loads((root / "datos/2_procesamiento/vigente/current.json").read_text())
    assert vigente["run_id"] == run_id
    assert set(result["manifest"]["fingerprints"]) == {"ingesta", "parametros"}
    assert result["graft"] == {}  # nothing published before: nothing to freeze


def test_repeating_without_changes_does_nothing(root):
    _go(root)
    folders = sorted((root / "datos/3_salida").glob("*"))
    again = _go(root, step=5, shift=7.0)  # the runner would change numbers
    assert again["plan"]["status"] == "NO_CHANGES"
    assert "manifest" not in again
    assert sorted((root / "datos/3_salida").glob("*")) == folders


def test_dry_run_only_plans(root):
    _go(root)
    (root / "datos/1_ingesta/geih_septiembre.xlsx").write_bytes(b"new")
    before = sorted((root / "datos/3_salida").glob("*"))
    plan = _go(root, step=5, dry_run=True)["plan"]
    assert plan["status"] == "RUN"
    assert plan["inputs"]["added"] == ["datos/1_ingesta/geih_septiembre.xlsx"]
    assert sorted((root / "datos/3_salida").glob("*")) == before


def test_new_annex_keeps_frozen_year_and_updates_open_year(root):
    first = _go(root)
    (root / "datos/1_ingesta/dept_2026.xlsx").write_bytes(b"annex-2026")
    second = _go(root, step=10, shift=5.0)
    assert second["plan"]["status"] == "RUN"
    for product in ("labor.departamentos", "informalidad.departamentos"):
        old = _delivered(root, first, product, "census").set_index(["period", "dep_code"])
        new = _delivered(root, second, product, "census").set_index(["period", "dep_code"])
        frozen = old.index.get_level_values("period") == FROZEN_MONTH
        assert old[frozen].equals(new.loc[old.index[frozen]]), product
        opened = ~frozen
        assert not old[opened].equals(new.loc[old.index[opened]]), product
    for report in second["graft"].values():
        assert report["frozen_cells_changed_in_output"] == 0
        assert report["frozen_cells_a_recomputation_would_have_changed"] > 0


def test_modified_existing_input_blocks_unless_accepted(root):
    _go(root)
    (root / "datos/1_ingesta/geih_agosto.xlsx").write_bytes(b"edited")
    blocked = _go(root, step=5, shift=1.0)
    assert blocked["plan"]["status"] == "BLOCKED"
    assert "geih_agosto.xlsx" in blocked["plan"]["blockers"][0]
    allowed = _go(root, step=6, shift=1.0, accept_modified=True)
    assert allowed["plan"]["status"] == "RUN"


def test_frozen_parameter_change_blocks_anchored_but_not_total(root):
    _go(root)
    (root / "datos/2_procesamiento/parametros_congelados/priors.csv").write_text("other")
    assert _go(root, step=5, shift=1.0)["plan"]["status"] == "BLOCKED"
    total = _go(root, "total", step=6, shift=1.0, confirm_total=True)
    assert total["plan"]["status"] == "RUN"


def test_total_requires_confirmation_and_rewrites_frozen_years(root):
    first = _go(root)
    unconfirmed = _go(root, "total", step=5, shift=3.0)
    assert unconfirmed["plan"]["status"] == "BLOCKED"
    assert "--confirm-total" in unconfirmed["plan"]["blockers"][0]
    total = _go(root, "total", step=6, shift=3.0, confirm_total=True)
    old = _delivered(root, first, "labor.departamentos", "census").set_index(["period", "dep_code"])
    new = _delivered(root, total, "labor.departamentos", "census").set_index(["period", "dep_code"])
    frozen = old.index.get_level_values("period") == FROZEN_MONTH
    assert not old[frozen].equals(new.loc[old.index[frozen]])  # frozen year rewritten


def test_deliveries_never_overwrite_each_other(root):
    first = _go(root)
    (root / "datos/1_ingesta/extra.xlsx").write_bytes(b"x")
    with pytest.raises(FileExistsError):
        _go(root, step=0, shift=1.0)  # same second as the first delivery
    assert (root / "datos/3_salida" / first["manifest"]["run_id"]).is_dir()


def _annexes(root: Path, *names: str) -> None:
    for name in names:
        (root / "datos/1_ingesta" / name).write_bytes(name.encode())


def test_without_a_pair_of_annexes_nothing_runs(root):
    plan = _go(root, dry_run=True, require_annexes=True)["plan"]
    assert plan["status"] == "BLOCKED"
    assert "complete pair" in plan["blockers"][0]


def test_the_cutoff_is_what_the_annexes_support(root):
    # Any naming style works: the pair is found by period.
    _annexes(root, "Anexo GEIH Agosto 2026.xlsx", "geih_informalidad_2026-08.xlsx")
    plan = _go(root, dry_run=True, require_annexes=True)["plan"]
    assert plan["annexes"]["cutoff"] == "2026-08"
    assert plan["status"] in ("RUN", "NO_CHANGES")


def test_a_month_with_only_one_annex_is_pending_not_computed(root):
    _annexes(root, "geih_mercado_laboral_2026-08.xlsx", "geih_informalidad_2026-08.xlsx",
             "anex-GEIH-sep2026.xlsx")  # September labor annex, no informality yet
    plan = _go(root, dry_run=True, require_annexes=True)["plan"]
    assert plan["annexes"]["cutoff"] == "2026-08"
    assert plan["annexes"]["pending"]["only_mercado_laboral"] == ["2026-09"]
    assert plan["status"] != "BLOCKED"  # computed as far as both annexes reach


def test_a_complete_pair_beyond_the_run_cutoff_is_not_silently_ignored(root):
    _annexes(root, "geih_mercado_laboral_2026-09.xlsx", "geih_informalidad_2026-09.xlsx")
    plan = _go(root, dry_run=True, require_annexes=True)["plan"]
    assert plan["status"] == "BLOCKED"
    assert "2026-09" in plan["blockers"][0] and "--through 2026-09" in plan["blockers"][0]


def test_missing_the_annexes_of_the_run_cutoff_blocks(root):
    _annexes(root, "geih_mercado_laboral_2026-07.xlsx", "geih_informalidad_2026-07.xlsx")
    plan = _go(root, dry_run=True, require_annexes=True)["plan"]
    assert plan["status"] == "BLOCKED"
    assert "annexes of 2026-08 are missing" in plan["blockers"][0]


def test_a_workbook_that_declares_another_month_blocks_even_if_it_is_named_right(root, tmp_path):
    from tests.annexes import annex

    july_labor = annex("mercado_laboral", "2026-07")
    august_informality = annex("informality", "2026-08")
    if not (july_labor.is_file() and august_informality.is_file()):
        pytest.skip("DANE annexes not present")
    import shutil

    # The July workbook dropped in under the August name.
    shutil.copy2(july_labor, root / "datos/1_ingesta/geih_mercado_laboral_2026-08.xlsx")
    shutil.copy2(august_informality, root / "datos/1_ingesta/geih_informalidad_2026-08.xlsx")
    plan = _go(root, dry_run=True, require_annexes=True, verify_content=True)["plan"]
    assert plan["status"] == "BLOCKED"
    assert any("declares 2026-07" in b for b in plan["blockers"])


def test_notes_from_the_recomputation_reach_the_manifest(root):
    result = _go(root, notes=lambda: {"regime_splice": "enabled; break_month=2001-01; window_months=24"})
    note = result["manifest"]["inputs_note"]
    assert note["regime_splice"].startswith("enabled")
    assert note["recalculation_plan"] == result["plan"]["status"]


def test_notes_and_office_lock_files_in_the_ingestion_do_not_count_as_changes(root):
    first = _go(root)
    assert first["plan"]["status"] == "RUN"
    (root / "datos/1_ingesta/LEEME.md").write_text("notas")
    (root / "datos/1_ingesta/~$anexo_abierto.xlsx").write_bytes(b"lock")
    again = _go(root, dry_run=True)["plan"]
    assert again["status"] == "NO_CHANGES"
    assert again["inputs"]["added"] == []
