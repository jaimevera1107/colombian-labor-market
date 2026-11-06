"""Find the annexes in the ingestion folder and the cutoff they support.

A new month must not depend on how a file happens to be named. The file name
is only a *hint* that classifies the workbook (monthly labor annex, informality
annex, annual departmental annex) and proposes its period; the period that
counts is the one declared **inside** the workbook, and the two must agree.

Accepted names (any case, with or without accents or spaces)::

    geih_mercado_laboral_2026-09.xlsx      canonical
    geih_informalidad_2026-09.xlsx         canonical (rolling quarter ending in the month)
    geih_departamentos_2026.xlsx           canonical (last year covered)
    Anexo GEIH Septiembre 2026.xlsx        as downloaded from DANE
    Anexo GEIH Informalidad Septiembre 2026.xlsx
    anex-GEIH-sep2026.xlsx                 DANE web address style

The cutoff is the **last month for which both monthly annexes exist**
(``mercado_laboral`` and ``informalidad``): everything is computed as far as
the annexes reach, and no further.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

LABOR = "mercado_laboral"
INFORMALITY = "informalidad"
DEPARTMENTS = "departamentos"
KINDS = (LABOR, INFORMALITY, DEPARTMENTS)

#: Files in the ingestion folder that hold data (anything else is ignored).
DATA_SUFFIXES = frozenset({".xlsx", ".xls", ".xlsm", ".csv"})

_MONTHS = {
    "enero": 1, "ene": 1, "febrero": 2, "feb": 2, "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4, "mayo": 5, "may": 5, "junio": 6, "jun": 6,
    "julio": 7, "jul": 7, "agosto": 8, "ago": 8, "septiembre": 9, "sept": 9,
    "sep": 9, "setiembre": 9, "octubre": 10, "oct": 10, "noviembre": 11,
    "nov": 11, "diciembre": 12, "dic": 12,
}
_MONTH_WORDS = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})(?!\d)")
_WORD_YEAR = re.compile(rf"(?<![a-z])({_MONTH_WORDS})[\s_\-]*(\d{{4}})(?!\d)")
_YEAR_WORD = re.compile(rf"(?<!\d)(\d{{4}})[\s_\-]*({_MONTH_WORDS})(?![a-z])")
_YEAR = re.compile(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)")


class AmbiguousAnnexError(ValueError):
    """Two different files claim the same annex and period."""


@dataclass(frozen=True)
class Annex:
    """One annex found in the ingestion folder.

    Attributes
    ----------
    kind : str
        ``mercado_laboral``, ``informalidad`` or ``departamentos``.
    period : str
        ``YYYY-MM`` for the monthly annexes, ``YYYY`` for the departmental one.
    path : Path
        Where the workbook is.
    current_format : bool
        ``False`` for binary ``.xls`` workbooks (historical archives), which
        never decide the cutoff.
    """

    kind: str
    period: str
    path: Path
    current_format: bool = True


def _plain(text: str) -> str:
    """Lowercase, accent-free, with separators normalised to spaces."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[_\.]+", " ", stripped.lower())


def parse_period(name: str) -> str | None:
    """Return ``YYYY-MM`` proposed by a file name, or ``None``."""
    text = _plain(Path(name).stem)
    match = _ISO.search(text)
    if match and 1 <= int(match.group(2)) <= 12:
        return f"{match.group(1)}-{match.group(2)}"
    match = _WORD_YEAR.search(text)
    if match:
        return f"{match.group(2)}-{_MONTHS[match.group(1)]:02d}"
    match = _YEAR_WORD.search(text)
    if match:
        return f"{match.group(1)}-{_MONTHS[match.group(2)]:02d}"
    return None


def is_workbook(path: Path) -> bool:
    """True for a real data workbook: not a hidden file, not an Office lock file.

    Excel writes ``~$<name>.xlsx`` next to a workbook while it is open; those
    files are not data and must never count as an annex or as an input.
    """
    name = Path(path).name
    return (
        not name.startswith(("~$", "."))
        and Path(name).suffix.lower() in DATA_SUFFIXES
    )


def classify(name: str) -> tuple[str, str] | None:
    """Return ``(kind, period)`` for a file name, or ``None`` if it is not an annex."""
    if not is_workbook(Path(name)):
        return None
    text = _plain(Path(name).stem)
    if "geih" not in text and "anex" not in text:
        return None
    if "informalidad" in text or "informal" in text:
        period = parse_period(name)
        return (INFORMALITY, period) if period else None
    if "departament" in text:
        match = _YEAR.search(text)
        return (DEPARTMENTS, match.group(1)) if match else None
    period = parse_period(name)
    return (LABOR, period) if period else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover(folder: Path) -> dict[str, list[Annex]]:
    """List every annex under ``folder``, grouped by kind and sorted by period.

    Identical copies (same bytes) are one annex. Two different files that
    claim the same kind and period raise ``AmbiguousAnnexError``.
    """
    found: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for path in sorted(Path(folder).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".xlsx", ".xls"} or not is_workbook(path):
            continue
        label = classify(path.name)
        if label is not None:
            found[label].append(path)
    grouped: dict[str, list[Annex]] = {kind: [] for kind in KINDS}
    for (kind, period), paths in found.items():
        # Prefer the current format; only identical files may share a slot.
        paths.sort(key=lambda p: (p.suffix.lower() != ".xlsx", str(p)))
        modern = [p for p in paths if p.suffix.lower() == ".xlsx"]
        chosen = modern or paths
        if len({_sha256(p) for p in chosen}) > 1:
            raise AmbiguousAnnexError(
                f"{kind} {period}: different files claim it: " + ", ".join(str(p) for p in chosen)
            )
        grouped[kind].append(
            Annex(kind, period, chosen[0], chosen[0].suffix.lower() == ".xlsx")
        )
    for annexes in grouped.values():
        annexes.sort(key=lambda a: a.period)
    return grouped


def detect_cutoff(folder: Path, upto: str | None = None) -> dict:
    """Return the last month both monthly annexes cover, and what is pending.

    Parameters
    ----------
    folder : Path
        The ingestion folder.
    upto : str, optional
        ``YYYY-MM``. When given, annexes of later months are ignored (as if they were not there): the user
        chose to work up to that month on purpose.

    Returns
    -------
    dict
        ``cutoff`` (``YYYY-MM`` or ``None``), the latest month of each annex
        kind, and ``pending``: months that have only one of the two annexes
        and therefore are not computed yet.
    """
    grouped = discover(folder)
    labor = {a.period for a in grouped[LABOR] if a.current_format and (upto is None or a.period <= upto)}
    informality = {a.period for a in grouped[INFORMALITY] if a.current_format and (upto is None or a.period <= upto)}
    both = labor & informality
    return {
        "cutoff": max(both) if both else None,
        "latest_mercado_laboral": max(labor) if labor else None,
        "latest_informalidad": max(informality) if informality else None,
        "pending": {
            "only_mercado_laboral": sorted(m for m in labor - informality if not both or m > max(both)),
            "only_informalidad": sorted(m for m in informality - labor if not both or m > max(both)),
        },
    }


def annexes_after(folder: Path, cutoff: str) -> set[Path]:
    """Monthly annex files of months later than ``cutoff`` (they do not belong to a run that ends at ``cutoff``)."""
    grouped = discover(folder)
    return {
        annex.path.resolve()
        for kind in (LABOR, INFORMALITY)
        for annex in grouped[kind]
        if annex.period > cutoff
    }


def annex_for(folder: Path, kind: str, period: str) -> Annex:
    """Return the annex of ``kind`` for ``period`` or raise ``FileNotFoundError``."""
    for annex in discover(folder)[kind]:
        if annex.period == period and annex.current_format:
            return annex
    raise FileNotFoundError(f"No {kind} annex for {period} in {folder}")
