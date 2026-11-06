"""Everyday commands: what each one decides, with a synthetic project and a simulated recalculation."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from icml.cli import project as cli
from icml.domain.cutoff import ACTIVE_CUTOFF, FROZEN_CUTOFF
from icml.ingestion.discovery import annexes_after, detect_cutoff
from icml.recalculation.runner import _ingestion_files, recalculate
from tests.unit.test_recalculation_runner import _runner

MONTHS = ("2026-06", "2026-07", "2026-08")


def _annex(root: Path, kind: str, month: str) -> None:
    folder = root / "datos/1_ingesta" / ("geih_mercado_laboral" if kind == "ml" else "geih_informalidad")
    folder.mkdir(parents=True, exist_ok=True)
    name = f"geih_{'mercado_laboral' if kind == 'ml' else 'informalidad'}_{month}.xlsx"
    (folder / name).write_bytes(f"{kind}-{month}".encode())


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"icml\"\n")
    (tmp_path / "datos/2_procesamiento/parametros_congelados").mkdir(parents=True)
    (tmp_path / "datos/2_procesamiento/parametros_congelados/p.csv").write_text("p")
    for month in MONTHS:
        for kind in ("ml", "inf"):
            _annex(tmp_path, kind, month)
    return tmp_path


def _publish(root: Path, cutoff: str, mode: str = "total") -> None:
    run_id = f"2026-11-03_000000_corte-{cutoff}_{mode}"
    (root / "datos/3_salida" / run_id).mkdir(parents=True)
    (root / "datos/3_salida" / run_id / "MANIFEST.json").write_text(json.dumps({"cutoff": cutoff}))
    (root / "datos/2_procesamiento/vigente").mkdir(parents=True, exist_ok=True)
    (root / "datos/2_procesamiento/vigente/vigente.json").write_text(json.dumps({"run_id": run_id, "mode": mode}))


def _args(**kw) -> argparse.Namespace:
    base = {"root": None, "through": None, "yes": False, "dry_run": False, "no_simple": True}
    return argparse.Namespace(**{**base, **kw})


def _plan(status: str, **extra) -> dict:
    return {"mode": "x", "status": status, "frozen_years": "frozen through 2025", "inputs": {}, "blockers": [], **extra}


class Calls:
    """Replaces ``run_recalculation`` and records how it was called."""

    def __init__(self, status: str = "EJECUTAR") -> None:
        self.status, self.calls = status, []

    def __call__(self, root, mode, **kw):
        self.calls.append({"mode": mode, **kw})
        result = {"plan": _plan(self.status, mode=mode)}
        if self.status == "EJECUTAR" and not kw.get("dry_run"):
            result["manifest"] = {"run_id": "2026-11-03_010101_corte-2026-08_total"}
        return result


@pytest.fixture
def recalc(monkeypatch):
    fake = Calls()
    monkeypatch.setattr("icml.recalculation.service.run_recalculation", fake)
    monkeypatch.setattr(cli, "_finish", lambda root, folder, make_simple: 0)
    return fake


# ------------------------------------------------------------------ project and state


def test_the_project_is_found_from_a_subfolder_and_a_wrong_folder_is_explained(project, tmp_path, monkeypatch):
    sub = project / "datos/1_ingesta"
    monkeypatch.chdir(sub)
    assert cli.find_project_root(None) == project.resolve()
    assert cli.find_project_root(project) == project.resolve()
    with pytest.raises(FileNotFoundError, match="Project folder"):
        cli.find_project_root(tmp_path / "otro")


def test_the_published_vintage_reports_its_cutoff_even_if_an_old_file_lacks_it(project):
    assert cli.current_vintage(project) is None
    _publish(project, "2026-07")
    assert cli.current_vintage(project)["cutoff"] == "2026-07"
    (project / "datos/2_procesamiento/vigente/vigente.json").write_text(json.dumps({"run_id": "x", "mode": "total", "cutoff": "2026-06"}))
    assert cli.current_vintage(project)["cutoff"] == "2026-06"


def test_a_month_must_look_like_a_month():
    assert cli._check_month("2026-07") == "2026-07" and cli._check_month(None) is None
    for bad in ("2026-7", "julio", "2026-13"):
        with pytest.raises(ValueError, match="YYYY-MM"):
            cli._check_month(bad)


@pytest.mark.parametrize(
    ("setup", "expected"),
    [
        (lambda p: None, "icml rebuild"),
        (lambda p: _publish(p, "2026-07"), "icml update"),
        (lambda p: _publish(p, "2026-08"), "up to date"),
    ],
)
def test_status_suggests_the_next_step(project, capsys, setup, expected):
    setup(project)
    assert cli.command_status(project) == 0
    assert expected in capsys.readouterr().out


def test_status_says_when_there_is_nothing_to_compute(tmp_path, capsys):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"icml\"\n")
    (tmp_path / "datos/1_ingesta").mkdir(parents=True)
    cli.command_status(tmp_path)
    assert "Copy both annexes" in capsys.readouterr().out


def test_status_notes_that_annexes_beyond_the_frozen_vintage_carry_parameters_forward(project, capsys):
    for kind in ("ml", "inf"):
        _annex(project, kind, "2026-09")
    cli.command_status(project)
    out = capsys.readouterr().out
    assert "2026-09" in out and "carried forward" in out and "icml rebuild" in out


# ------------------------------------------------------------------ the cutoff cap


def test_the_detector_can_ignore_later_months(project):
    assert detect_cutoff(project / "datos/1_ingesta")["cutoff"] == "2026-08"
    assert detect_cutoff(project / "datos/1_ingesta", "2026-07")["cutoff"] == "2026-07"
    later = {p.name for p in annexes_after(project / "datos/1_ingesta", "2026-07")}
    assert later == {"geih_mercado_laboral_2026-08.xlsx", "geih_informalidad_2026-08.xlsx"}


def test_an_annex_added_after_a_run_is_a_new_input_not_something_it_already_used(project):
    """The trap: consolidate up to July with August already in the folder, then update with August."""
    now = datetime(2026, 11, 3, 10, 0, tzinfo=UTC)
    first = recalculate(
        project, "total", anchor_year=2025, runner=_runner(0.0), confirm_total=True, now=now, check_shapes=False,
        cutoff="2026-07", upto="2026-07", require_annexes=False, verify_content=False,
    )
    listed = set(first["manifest"]["fingerprints"]["ingesta"])
    assert not any("2026-08" in name for name in listed) and any("2026-07" in name for name in listed)
    vigente = json.loads((project / "datos/2_procesamiento/vigente/vigente.json").read_text())
    assert vigente["cutoff"] == "2026-07"
    second = recalculate(
        project, "anclado", anchor_year=2025, runner=_runner(1.0), now=now + timedelta(minutes=5), check_shapes=False,
        require_annexes=False, verify_content=False, dry_run=True,
    )
    assert second["plan"]["status"] == "EJECUTAR"  # not SIN_CAMBIOS
    assert {Path(p).name for p in second["plan"]["inputs"]["added"]} == {"geih_mercado_laboral_2026-08.xlsx", "geih_informalidad_2026-08.xlsx"}


def test_without_a_cap_later_annexes_count_as_inputs(project):
    assert len(_ingestion_files(project / "datos/1_ingesta")) == 6
    assert len(_ingestion_files(project / "datos/1_ingesta", "2026-07")) == 4


# ------------------------------------------------------------------ rebuild


def test_rebuild_over_a_published_vintage_asks_for_confirmation(project, recalc, capsys, monkeypatch):
    _publish(project, "2026-08")
    monkeypatch.setattr("sys.stdin", type("NoTty", (), {"isatty": lambda self: False})())
    assert cli.command_run(project, "rebuild", _args(through="2026-08")) == cli.EXIT_ACTION
    out = capsys.readouterr().out
    assert "icml update" in out and "--yes" in out and not recalc.calls  # no terminal and no --yes: nothing runs
    assert cli.command_run(project, "rebuild", _args(through="2026-08", yes=True)) == 0
    call = recalc.calls[0]
    assert call["mode"] == "total" and call["confirm_total"] is True and call["dry_run"] is False


def test_the_first_rebuild_needs_no_confirmation(project, recalc):
    assert cli.command_run(project, "rebuild", _args(through="2026-08")) == 0
    assert recalc.calls[0]["mode"] == "total"


def test_a_dry_run_never_asks_and_never_computes(project, recalc, capsys):
    _publish(project, "2026-08")
    assert cli.command_run(project, "rebuild", _args(through="2026-08", dry_run=True)) == 0
    assert recalc.calls[0]["dry_run"] is True and "Dry run" in capsys.readouterr().out


def test_another_month_restarts_the_program_with_that_cutoff(project, monkeypatch):
    seen = []
    monkeypatch.setattr(cli, "_relaunch", lambda root, command, args, target: seen.append((command, target)) or 0)
    assert ACTIVE_CUTOFF == FROZEN_CUTOFF
    assert cli.command_run(project, "rebuild", _args(through="2026-07")) == 0
    assert seen == [("rebuild", "2026-07")]


def test_without_through_it_uses_the_last_complete_month(project, monkeypatch):
    for kind in ("ml", "inf"):
        for month in ("2026-07", "2026-08"):
            (project / f"datos/1_ingesta/geih_{'mercado_laboral' if kind == 'ml' else 'informalidad'}/geih_{'mercado_laboral' if kind == 'ml' else 'informalidad'}_{month}.xlsx").unlink()
    seen = []
    monkeypatch.setattr(cli, "_relaunch", lambda root, command, args, target: seen.append(target) or 0)
    cli.command_run(project, "rebuild", _args())
    assert seen == ["2026-06"]


def test_a_month_without_both_annexes_is_explained(project, recalc, capsys):
    (project / "datos/1_ingesta/geih_informalidad/geih_informalidad_2026-07.xlsx").unlink()
    assert cli.command_run(project, "rebuild", _args(through="2026-07")) == cli.EXIT_ACTION
    assert "Both annexes of 2026-07" in capsys.readouterr().out and not recalc.calls


def test_a_month_after_the_frozen_vintage_restarts_with_that_cutoff_and_says_parameters_are_extended(project, monkeypatch, capsys):
    for kind in ("ml", "inf"):
        _annex(project, kind, "2026-09")
    seen = []
    monkeypatch.setattr(cli, "_relaunch", lambda root, command, args, target: seen.append(target) or 0)
    assert cli.command_run(project, "rebuild", _args()) == 0
    assert seen == ["2026-09"] and "carried forward" in capsys.readouterr().out


# ------------------------------------------------------------------ update


def test_update_needs_a_published_vintage(project, recalc, capsys):
    assert cli.command_run(project, "update", _args()) == cli.EXIT_ACTION
    assert "icml rebuild" in capsys.readouterr().out and not recalc.calls


def test_update_only_updates_and_says_so(project, recalc, capsys):
    _publish(project, "2026-07")
    assert cli.command_run(project, "update", _args()) == 0
    assert recalc.calls[0]["mode"] == "anclado" and recalc.calls[0]["confirm_total"] is False
    assert "UPDATE ONLY" in capsys.readouterr().out


def test_update_does_not_go_back(project, recalc, capsys):
    _publish(project, "2026-08")
    assert cli.command_run(project, "update", _args(through="2026-07")) == cli.EXIT_ACTION
    assert "does not go back" in capsys.readouterr().out and not recalc.calls


def test_nothing_new_is_reported_as_up_to_date(project, capsys, monkeypatch):
    _publish(project, "2026-08")
    monkeypatch.setattr("icml.recalculation.service.run_recalculation", Calls("SIN_CAMBIOS"))
    assert cli.command_run(project, "update", _args()) == 0
    assert "up to date" in capsys.readouterr().out


def test_a_blocked_plan_is_an_action_for_the_user_not_a_crash(project, capsys, monkeypatch):
    _publish(project, "2026-07")

    def blocked(root, mode, **kw):
        return {"plan": _plan("BLOQUEADO", blockers=["An existing input was modified"])}

    monkeypatch.setattr("icml.recalculation.service.run_recalculation", blocked)
    assert cli.command_run(project, "update", _args()) == cli.EXIT_ACTION
    assert "BLOCKED: An existing input was modified" in capsys.readouterr().out


# ------------------------------------------------------------------ plots, verify, mistakes


def test_plots_draws_the_published_delivery_and_passes_the_options(project, monkeypatch, capsys):
    _publish(project, "2026-08")
    received = {}

    class Tool:
        GROUPS = ("nacional", "departamentos", "comparativos")
        UNIVERSES = ("censo", "geih")
        PlotsExist = FileExistsError

        @staticmethod
        def render_delivery(folder, output=None, **options):
            received["folder"], received["options"] = folder, options
            return folder.with_name(folder.name + "_graficos"), 3

    monkeypatch.setitem(__import__("sys").modules, "icml.plots.delivery", Tool)
    args = argparse.Namespace(folder=None, only="nacional", universe="censo", departments="05,11", format="pdf", force=True)
    assert cli.command_plots(project, args) == 0
    assert received["folder"].name.endswith("corte-2026-08_total")
    options = received["options"]
    assert options["groups"] == ("nacional",) and options["universes"] == ("censo",)
    assert options["departments"] == ("05", "11") and options["fmt"] == "pdf" and options["force"] is True
    assert "INDICE.html" in capsys.readouterr().out


def test_plots_without_any_delivery_says_what_to_do_first(project, monkeypatch):
    pytest.importorskip("matplotlib")
    args = argparse.Namespace(folder=None, only=None, universe=None, departments=None, format="png", force=False)
    with pytest.raises(FileNotFoundError, match="icml rebuild"):
        cli.command_plots(project, args)


def test_a_user_mistake_prints_a_plain_message_and_not_a_traceback(tmp_path, capsys):
    args = argparse.Namespace(command="status", root=tmp_path)
    assert cli.run_command(args) == cli.EXIT_ERROR
    assert "Project folder" in capsys.readouterr().err
    bad = argparse.Namespace(command="rebuild", root=None, through="july")
    assert cli.run_command(argparse.Namespace(**{**vars(bad), "root": tmp_path})) == cli.EXIT_ERROR


def test_the_commands_are_registered_in_the_main_program():
    from icml.cli import build_parser

    parser = build_parser()
    for command in cli.COMMANDS:
        assert parser.parse_args([command]).command == command
    parsed = parser.parse_args(["rebuild", "--through", "2026-07", "--yes"])
    assert parsed.through == "2026-07" and parsed.yes and parsed.handler is cli.run_command


def test_update_accepts_month_as_the_month_to_include():
    from icml.cli import build_parser

    parsed = build_parser().parse_args(["update", "--month", "2026-08", "--dry-run"])
    assert parsed.through == "2026-08" and parsed.dry_run
    assert build_parser().parse_args(["update", "--through", "2026-08"]).through == "2026-08"
