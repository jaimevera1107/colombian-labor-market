"""The layout migration moves, never deletes, and rewrites references."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "release" / "reorganize_layout.py"
spec = importlib.util.spec_from_file_location("reorganize_layout", TOOL)
layout = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = layout  # dataclasses resolves the module by name
spec.loader.exec_module(layout)


def _write(root: Path, relative: str, text: str = "x") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path: Path) -> Path:
    _write(tmp_path, "insumos/fuentes/dane/geih/Anexo.xlsx", "annex")
    _write(tmp_path, "insumos/fuentes/historicas/nacional/enh.csv", "enh")
    _write(tmp_path, "insumos/sectorial/anexos_historicos/a.xls", "xls")
    _write(tmp_path, "insumos/sectorial/anexos_historicos/b.csv", "csv")
    _write(tmp_path, "insumos/catalogo_fuentes.json", '{"p": "insumos/laboral/c.csv"}')
    _write(tmp_path, "insumos/laboral/c.csv", "lab")
    _write(tmp_path, "informalidad/secuencia_v003/02_nacionales.csv", "seq")
    _write(tmp_path, "validacion/rc1_original/fases/g.csv", "gold")
    _write(tmp_path, "ENTREGA_H36/leer.md", "doc")
    _write(tmp_path, "LEER_PRIMERO.md", "root doc")
    _write(tmp_path, "dependencias/w.whl", "wheel")
    _write(
        tmp_path,
        "icml-colombia/src/icml/m.py",
        'A = "insumos/fuentes/historicas/nacional/enh.csv"\n'
        'B = root / "informalidad/secuencia_v003"\n'
        'C = rel.endswith("secuencia_v003/02_nacionales.csv")\n'
        'D = "validacion/rc1_original"\n',
    )
    return tmp_path


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("insumos/fuentes/dane/geih/Anexo.xlsx", "datos/1_ingesta/dane/geih/Anexo.xlsx"),
        ("insumos/sectorial/anexos_historicos/a.xls", "datos/1_ingesta/excel_originales/Mercado Laboral/Anexos sectoriales historicos/a.xls"),
        ("insumos/sectorial/anexos_historicos/b.csv", "datos/2_procesamiento/fuentes_preparadas/sectorial/anexos_historicos/b.csv"),
        ("informalidad/secuencia_v003/02_nacionales.csv", "datos/2_procesamiento/parametros_congelados/informalidad_secuencia_h5_h6/02_nacionales.csv"),
        ("insumos/laboral/ciudades.csv", "datos/2_procesamiento/productos_congelados/laboral/ciudades.csv"),
        ("validacion/rc1_original/x.csv", "legacy/validacion/rc1_original/x.csv"),
        ("research/sectoral/h16/src/m.py", "legacy/research_h16_src_copia/m.py"),
        ("research/sectoral/h16/inputs/d.csv", "datos/2_procesamiento/sectorial_h16/inputs/d.csv"),
    ],
)
def test_rules_place_each_kind_of_file(old, new):
    assert layout.destination_for(old)[0] == new


def test_dry_run_plan_has_no_unclassified_files(project):
    moves, unclassified = layout.build_plan(project)
    assert unclassified == []
    moved = {m.source for m in moves}
    assert "LEER_PRIMERO.md" not in moved
    assert not any(s.startswith(("dependencias/", "icml-colombia/")) for s in moved)


def test_unclassified_file_is_reported_not_moved(project):
    _write(project, "insumos/algo_nuevo/z.csv")
    _, unclassified = layout.build_plan(project)
    assert unclassified == ["insumos/algo_nuevo/z.csv"]


def test_apply_moves_every_file_and_deletes_nothing(project):
    before = {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    moves, _ = layout.build_plan(project)
    migration = layout.apply_plan(project, moves)
    assert migration["deleted"] == 0
    mapping = {e["old"]: e["new"] for e in migration["entries"]}
    for old, content in before.items():
        target = mapping.get(old, old)
        assert (project / target).read_bytes() == content, old
    assert not (project / "insumos").exists()  # emptied folders are removed
    assert json.loads((project / "datos/MAPA_MIGRACION.json").read_text())["files_moved"] == len(moves)
    assert (project / "datos/3_salida").is_dir()


def test_rewrite_follows_files_and_is_idempotent(project):
    moves, _ = layout.build_plan(project)
    layout.apply_plan(project, moves)
    changed = layout.rewrite_references(project, moves)
    code = (project / "icml-colombia/src/icml/m.py").read_text()
    assert 'A = "datos/2_procesamiento/fuentes_preparadas/nacional/enh.csv"' in code
    assert 'B = root / "datos/2_procesamiento/parametros_congelados/informalidad_secuencia_h5_h6"' in code
    assert 'D = "legacy/validacion/rc1_original"' in code
    assert any(k.endswith("m.py") for k in changed)
    catalog = project / "datos/2_procesamiento/catalogos/catalogo_fuentes.json"
    assert "datos/2_procesamiento/productos_congelados/laboral/c.csv" in catalog.read_text()
    # Running again must change nothing (no stacked ``legacy/legacy``).
    assert layout.rewrite_references(project, moves) == {}
    assert "legacy/legacy" not in (project / "icml-colombia/src/icml/m.py").read_text()


def test_partial_check_with_an_old_folder_name_is_reported(project):
    # The exact pattern of the bug found in integral.py: a *suffix* such as
    # ``rel.endswith("secuencia_v003/02_nacionales.csv")`` is not a full
    # path, so no replacement fixes it and it silently stops matching.
    moves, _ = layout.build_plan(project)
    layout.apply_plan(project, moves)
    layout.rewrite_references(project, moves)
    left = layout.leftover_references(project, moves)
    assert left == {"icml-colombia/src/icml/m.py": ["secuencia_v003"]}


def test_no_leftovers_when_code_uses_only_new_names(project):
    moves, _ = layout.build_plan(project)
    layout.apply_plan(project, moves)
    code = project / "icml-colombia/src/icml/m.py"
    code.write_text('A = "x"\n', encoding="utf-8")
    assert layout.leftover_references(project, moves) == {}


def test_plan_rejects_existing_destination(project):
    moves, _ = layout.build_plan(project)
    _write(project, moves[0].destination)
    assert any("already exists" in p for p in layout.check_plan(project, moves))


def test_main_dry_run_changes_nothing(project, capsys):
    before = sorted(p.relative_to(project).as_posix() for p in project.rglob("*"))
    assert layout.main(["--root", str(project)]) == 0
    assert sorted(p.relative_to(project).as_posix() for p in project.rglob("*")) == before
    assert "Dry run" in capsys.readouterr().out
