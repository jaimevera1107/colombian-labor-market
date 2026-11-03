"""verify_checkout: a copy is complete and intact only if every listed byte is there."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "release" / "verify_checkout.py"
spec = importlib.util.spec_from_file_location("verify_checkout", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


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


def test_the_command_line_exit_codes(repo, capsys):
    assert tool.main(["--raiz", str(repo), "--escribir"]) == 0
    assert tool.main(["--raiz", str(repo)]) == 0
    (repo / "nuevo.txt").write_text("extra")
    assert tool.main(["--raiz", str(repo)]) == 0
    assert tool.main(["--raiz", str(repo), "--estricto"]) == 1
    (repo / "README.md").write_text("cambiado")
    assert tool.main(["--raiz", str(repo)]) == 1
    assert "ALTERADO: README.md" in capsys.readouterr().out


def test_verifying_without_a_listing_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        tool.verify(tmp_path)
