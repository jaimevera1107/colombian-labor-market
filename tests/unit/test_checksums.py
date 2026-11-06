"""checksums: a copy is complete and intact only if every listed byte is there."""

from __future__ import annotations

import pytest

from icml.operations import checksums as tool


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "datos/1_ingesta").mkdir(parents=True)
    (tmp_path / "datos/1_ingesta/a.csv").write_bytes(b"x,y\r\n1,2\r\n")  # CRLF must survive untouched
    (tmp_path / "datos/1_ingesta/Reconstrucci\u00f3n ENH 1993.xlsx").write_bytes(b"\x00\x01binary")
    (tmp_path / "README.md").write_text("hola", encoding="utf-8")
    return tmp_path


def test_listing_covers_the_tracked_files_and_ignores_caches_and_itself(repo):
    (repo / ".git").mkdir()
    (repo / ".git/config").write_text("x")
    (repo / "pkg/__pycache__").mkdir(parents=True)
    (repo / "pkg/__pycache__/m.pyc").write_bytes(b"x")
    (repo / "datos/1_ingesta/~$a.xlsx").write_bytes(b"lock")
    (repo / "datos/2_procesamiento/_corridas").mkdir(parents=True)
    (repo / "datos/2_procesamiento/_corridas/run1.csv").write_text("temporary")
    (repo / "datos/2_procesamiento/_corridas/.gitkeep").write_text("")
    count = tool.write_listing(repo)
    names = {line.split("  ", 1)[1] for line in (repo / "SHA256SUMS").read_text("utf-8").splitlines()}
    assert count == 4
    assert names == {"README.md", "datos/1_ingesta/a.csv", "datos/1_ingesta/Reconstrucci\u00f3n ENH 1993.xlsx",
                     "datos/2_procesamiento/_corridas/.gitkeep"}


def test_a_complete_copy_verifies_and_a_changed_byte_does_not(repo):
    tool.write_listing(repo)
    assert tool.verify(repo)["complete"]
    (repo / "datos/1_ingesta/a.csv").write_bytes(b"x,y\n1,2\n")  # what a CRLF->LF conversion would do
    result = tool.verify(repo)
    assert not result["complete"] and result["altered"] == ["datos/1_ingesta/a.csv"]


def test_a_missing_file_is_reported_and_an_extra_one_is_only_a_warning(repo):
    tool.write_listing(repo)
    (repo / "README.md").unlink()
    (repo / "nuevo.txt").write_text("extra")
    result = tool.verify(repo)
    assert result["missing"] == ["README.md"] and result["extra"] == ["nuevo.txt"] and not result["complete"]
    (repo / "README.md").write_text("hola", encoding="utf-8")
    assert tool.verify(repo)["complete"]  # an extra file alone does not make the copy incomplete


def test_generated_outputs_are_never_listed(repo):
    (repo / "datos/2_procesamiento/vigente").mkdir(parents=True)
    (repo / "datos/2_procesamiento/vigente/labor.csv").write_text("generated")
    (repo / "datos/3_salida/2026-11-05_000000_corte-2026-07_total").mkdir(parents=True)
    (repo / "datos/3_salida/2026-11-05_000000_corte-2026-07_total/MANIFEST.json").write_text("{}")
    (repo / "datos/3_salida/LEEME.txt").write_text("placeholder")
    names = {p.as_posix() for p in tool.tracked_files(repo)}
    assert "datos/3_salida/LEEME.txt" in names
    assert not any(n.startswith(("datos/2_procesamiento/vigente/", "datos/3_salida/2026")) for n in names)


def test_the_command_line_exit_codes(repo, capsys):
    import argparse

    from icml.cli.project import command_checksums

    def run(*flags):
        return command_checksums(repo, argparse.Namespace(write="--write" in flags, strict="--strict" in flags))

    assert run("--write") == 0
    assert run() == 0
    (repo / "nuevo.txt").write_text("extra")
    assert run() == 0
    assert run("--strict") == 1
    (repo / "README.md").write_text("cambiado")
    assert run() == 1
    assert "ALTERED: README.md" in capsys.readouterr().out


def test_verifying_without_a_listing_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        tool.verify(tmp_path)
