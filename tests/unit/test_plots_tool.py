"""Optional plotting tool: figures for a delivery, readable and never wrong about gaps."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("matplotlib")

PROJECT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parents[2] / "tools" / "plots" / "graficar_entrega.py"
spec = importlib.util.spec_from_file_location("graficar_entrega", TOOL)
tool = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tool  # dataclasses look the module up by name
spec.loader.exec_module(tool)

PNG = b"\x89PNG\r\n\x1a\n"
DEPARTMENTS = {"05": "Antioquia", "11": "Bogotá D.C.", "99": "Vichada"}
MONTHS = pd.date_range("2000-01-01", "2004-12-01", freq="MS")
META = tool.Meta(cutoff="2004-12", version="9.9.9", run_id="entrega-de-prueba")


def make_frames() -> dict:
    """Two universes, national and 3 departments; Vichada has no GEIH representation in 2001-2003."""
    rng = np.random.default_rng(1)
    frames = {}
    for universe in tool.UNIVERSES:
        for level, codes in (("nacional", [None]), ("departamentos", list(DEPARTMENTS))):
            labor, informal, sector = [], [], []
            for code in codes:
                for k, date in enumerate(MONTHS):
                    unrepresented = universe == "geih" and code == "99" and pd.Timestamp("2001-01-01") <= date <= pd.Timestamp("2003-12-01")
                    pet = 0.0 if unrepresented else 1e6 * (1 + 0.01 * k) * (3 if code is None else 1)
                    pea, occ = 0.7 * pet, 0.62 * pet
                    base = {"Fecha": date, "Año": date.year, "Mes": date.month}
                    if code is not None:
                        base |= {"DPT": DEPARTMENTS[code], "Codigo": code}
                    nan = np.nan
                    labor.append({**base, "Ocupados": occ, "Desocupados": pea - occ, "Inactivos": pet - pea, "PEA": pea, "PET": pet,
                                  "Poblacion": pet * 1.4, "TD": nan if unrepresented else (pea - occ) / pea if pea else nan,
                                  "TO": nan if unrepresented else 0.62, "TGP": nan if unrepresented else 0.7})
                    informal.append({**base, "Poblacion": pet * 1.4, "PET": pet, "PEA": pea, "Ocupados": occ, "Desocupados": pea - occ,
                                     "Inactivos": pet - pea, "Informales": 0.6 * occ, "Formales": 0.4 * occ,
                                     "TI": nan if unrepresented else 0.6 - 0.0005 * k})
                    shares = rng.dirichlet(np.ones(len(tool.SECTORS)))
                    for sec, share in zip(tool.SECTORS, shares, strict=True):
                        sector.append({**base, "Sector": sec, "Ocupados": occ * share, "Participacion": nan if unrepresented else share})
            frames[(universe, "laboral", level)] = pd.DataFrame(labor)
            frames[(universe, "informalidad", level)] = pd.DataFrame(informal)
            frames[(universe, "sectorial", level)] = pd.DataFrame(sector)
    return frames


@pytest.fixture(scope="module")
def frames():
    return make_frames()


# ------------------------------------------------------------------ pure helpers


def test_slug_is_ascii_and_stable():
    assert tool.slug("Bogotá D.C.") == "bogota-d-c"
    assert tool.slug("San Andrés y Providencia") == "san-andres-y-providencia"
    assert tool.slug("Norte de Santander") == "norte-de-santander"


@pytest.mark.parametrize(
    ("value", "divisor", "unit"),
    [(3.2e7, 1e6, "millones"), (4_500.0, 1e3, "miles"), (20.0, 1.0, "personas"), (float("nan"), 1.0, "personas")],
)
def test_units_keep_levels_readable(value, divisor, unit):
    got_divisor, got_unit = tool.scale_units(value)
    assert got_divisor == divisor and unit in got_unit


def test_spans_are_the_contiguous_runs_of_the_mask():
    dates = pd.Series(pd.date_range("2001-01-01", periods=6, freq="MS"))
    runs = tool.spans(pd.Series([False, True, True, False, True, True]), dates)
    assert runs == [(dates[1], dates[2]), (dates[4], dates[5])]
    assert tool.spans(pd.Series([False] * 6), dates) == []
    assert tool.spans(pd.Series([True] * 6), dates) == [(dates[0], dates[5])]


def test_annual_mean_is_by_territory_and_year(frames):
    table = tool.annual_mean(frames[("censo", "informalidad", "departamentos")], "TI")
    assert list(table.index) == list(DEPARTMENTS) and list(table.columns) == [2000, 2001, 2002, 2003, 2004]


def test_every_sector_has_a_name_and_a_stable_color():
    colors = tool.sector_colors(tool.SECTORS)
    assert set(colors) == set(tool.SECTORS) and all(tool.SECTOR_NAMES[c] for c in tool.SECTORS)
    assert colors["NO_INFO"] == "#9A9A9A"
    assert tool.sector_colors(["A"])["A"] == colors["A"]  # the color does not depend on which sectors are drawn
    assert tool.sector_label("ZZ") == "ZZ" and tool.sector_colors(["ZZ"])["ZZ"] == "#9A9A9A"


# ------------------------------------------------------------------ figures


def test_everything_is_drawn_for_both_universes(frames, tmp_path):
    items = tool.build_all(frames, tmp_path, META, tool.Options(dpi=40))
    names = {i.path.relative_to(tmp_path).as_posix() for i in items}
    for universe in tool.UNIVERSES:
        assert f"universo_{universe}/nacional.png" in names
        for code, dep in DEPARTMENTS.items():
            assert f"universo_{universe}/departamentos/{code}_{tool.slug(dep)}.png" in names
        assert f"comparativos/dispersion_departamental_{universe}.png" in names
    for rate in tool.RATES:
        assert {f"comparativos/departamentos_{rate}_censo_vs_geih.png", f"comparativos/ranking_{rate}.png",
                f"comparativos/mapa_calor_{rate}_censo.png", f"comparativos/mapa_calor_{rate}_geih.png"} <= names
    assert "comparativos/nacional_censo_vs_geih.png" in names
    assert len(items) == 2 * (1 + 3) + 1 + 4 * 4 + 2
    for item in items:
        data = item.path.read_bytes()
        assert data.startswith(PNG) and len(data) > 5_000, item.path


def test_the_options_narrow_what_is_drawn(frames, tmp_path):
    items = tool.build_all(frames, tmp_path, META, tool.Options(groups=("departamentos",), universes=("geih",), departments=("11",), dpi=40))
    assert [i.path.name for i in items] == ["11_bogota-d-c.png"]
    only_national = tool.build_all(frames, tmp_path / "n", META, tool.Options(groups=("nacional",), dpi=40))
    assert {i.universe for i in only_national} == {"censo", "geih"} and len(only_national) == 2


def test_a_territory_without_geih_representation_still_draws_and_says_so(frames, tmp_path):
    path = tmp_path / "vichada.png"
    assert tool.plot_dashboard(frames, "geih", code="99", name="Vichada", path=path, meta=META, dpi=40)
    assert path.read_bytes().startswith(PNG)


def test_a_missing_territory_is_not_drawn(frames, tmp_path):
    assert not tool.plot_dashboard(frames, "censo", code="77", name="Inexistente", path=tmp_path / "x.png", meta=META, dpi=40)
    assert not (tmp_path / "x.png").exists()


def test_comparatives_need_both_universes(frames, tmp_path):
    items = tool.build_all(frames, tmp_path, META, tool.Options(groups=("comparativos",), universes=("censo",), dpi=40))
    names = {i.path.name for i in items}
    assert "nacional_censo_vs_geih.png" not in names and "mapa_calor_TD_censo.png" in names
    assert not any("geih" in n for n in names)


def test_pdf_output_is_supported(frames, tmp_path):
    items = tool.build_all(frames, tmp_path, META, tool.Options(groups=("nacional",), universes=("censo",), fmt="pdf", dpi=40))
    assert items[0].path.suffix == ".pdf" and items[0].path.read_bytes().startswith(b"%PDF")


# ------------------------------------------------------------------ index and command line


def test_the_index_links_every_figure_and_escapes_titles(frames, tmp_path):
    items = tool.build_all(frames, tmp_path, META, tool.Options(groups=("nacional", "departamentos"), dpi=40))
    items[0].title = "<script>x</script>"
    index = tool.write_index(tmp_path, items, META)
    page = index.read_text("utf-8")
    assert all(i.path.relative_to(tmp_path).as_posix() in page for i in items)
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page
    assert "9.9.9" in page and (tmp_path / "LEEME.md").is_file()


def test_the_command_refuses_to_overwrite_and_validates_options(frames, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tool, "load_frames", lambda path: (frames, META))
    out = tmp_path / "salida"
    args = ["--carpeta", str(tmp_path), "--salida", str(out), "--solo", "nacional", "--dpi", "40"]
    assert tool.main(args) == 0 and (out / "INDICE.html").is_file()
    assert tool.main(args) == 2 and "--forzar" in capsys.readouterr().err
    (out / "viejo.txt").write_text("x")
    assert tool.main([*args, "--forzar"]) == 0 and not (out / "viejo.txt").exists()
    with pytest.raises(SystemExit) as exc:
        tool.main(["--carpeta", str(tmp_path), "--solo", "mapas"])
    assert exc.value.code == 2


# ------------------------------------------------------------------ the real delivery of the repository


def _delivery():
    found = sorted((PROJECT / "datos" / "3_salida").glob("*_total")) or sorted((PROJECT / "datos" / "3_salida").glob("*_anclado"))
    return found[-1] if found else None


@pytest.mark.skipif(_delivery() is None, reason="no delivery in datos/3_salida")
def test_the_real_delivery_loads_and_the_national_dashboards_draw(tmp_path):
    real, meta = tool.load_frames(_delivery())
    assert len(real) == 16 and len(tool.departments(real)) == 33
    assert meta.cutoff and meta.version
    out = tmp_path / "graficos"
    assert tool.main(["--carpeta", str(_delivery()), "--salida", str(out), "--solo", "nacional", "--dpi", "40"]) == 0
    assert (out / "universo_censo" / "nacional.png").read_bytes().startswith(PNG)
    assert (out / "universo_geih" / "nacional.png").is_file() and (out / "INDICE.html").is_file()
