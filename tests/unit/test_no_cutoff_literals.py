"""Guard: the August 2026 cutoff is defined once, in ``icml.domain.cutoff``.

Every remaining ``2026-08`` / ``2026_08`` occurrence in the package is
listed here with the reason it is legitimate. The count per file is a
ratchet: it may go down, but adding a new occurrence (or a new file with
one) fails this test, which is the signal to use ``icml.domain.cutoff``
instead of spelling the vintage out again.
"""

import re
import tokenize
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "icml"
PATTERN = re.compile(r"2026[-_]08")

ALLOWED = {
    # Definition of the constant and its documentation.
    "domain/cutoff.py": 3,
    # Docstrings describing the frozen vintage or source window.
    "operations/integral.py": 1,
    "sectoral/monthly.py": 1,
    # Identity of a frozen source role (name on disk), not a calendar: the
    # ``informality_current`` role of the original annex.
    "operations/excel_historical_sources.py": 1,  # docstring
    # Explicit months compared when checking official revisions.
    "operations/geih_intake.py": 1,
}


def _count(path: Path) -> int:
    return len(PATTERN.findall(path.read_text(encoding="utf-8")))


def test_cutoff_literals_do_not_grow():
    found = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        count = _count(path)
        if count:
            found[path.relative_to(PACKAGE).as_posix()] = count
    unexpected = {
        name: count
        for name, count in found.items()
        if count > ALLOWED.get(name, 0)
    }
    assert not unexpected, (
        "New hard-coded cutoff literal(s); use icml.domain.cutoff: "
        f"{unexpected}"
    )


def test_allowlist_has_no_stale_entries():
    # Keep the list honest: an entry that no longer matches must go.
    stale = [
        name
        for name, count in ALLOWED.items()
        if _count(PACKAGE / name) < count
    ]
    assert not stale, f"Tighten the allowlist for: {stale}"


# Panel shapes derive from the calendar: 404 months, 33 x 404 = 13332
# rows, 2 x 404 = 808 national rows, 13332 x 15 = 199980 sectoral rows.
SHAPE_NUMBERS = {"404", "13332", "13_332", "808", "199980"}


def _shape_number_tokens(path: Path) -> list[int]:
    """Return the line of every numeric *token* equal to a panel shape.

    Tokenizing (instead of searching text) leaves message strings such as
    ``'33 territories x 404 months'`` alone and flags only real code.
    """
    with path.open("rb") as stream:
        tokens = tokenize.tokenize(stream.readline)
        return [
            token.start[0]
            for token in tokens
            if token.type == tokenize.NUMBER and token.string in SHAPE_NUMBERS
        ]


def test_panel_shapes_come_from_the_cutoff_module():
    offenders = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(PACKAGE).as_posix()
        if relative == "domain/cutoff.py":
            continue
        lines = _shape_number_tokens(path)
        if lines:
            offenders[relative] = lines
    assert not offenders, (
        "Hard-coded panel shape(s); use N_MONTHS, ROWS_33 or "
        f"ROWS_NATIONAL from icml.domain.cutoff: {offenders}"
    )
