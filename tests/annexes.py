"""Locate the DANE annexes for tests by period, whatever the files are called."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from icml.ingestion.discovery import AmbiguousAnnexError, discover

PROJECT = Path(__file__).resolve().parents[1]
INGESTA = PROJECT / "datos" / "1_ingesta"


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return discover(INGESTA) if INGESTA.is_dir() else {}


def annex(kind: str, period: str) -> Path:
    """Return the annex of ``kind`` for ``period``.

    When it is not there (a lean checkout) a path that does not exist is
    returned, so ``skipif(not path.is_file())`` guards keep working.
    """
    try:
        for found in _catalog().get(kind, []):
            if found.period == period and found.current_format:
                return found.path
    except AmbiguousAnnexError:
        pass
    return INGESTA / "__missing__" / f"{kind}_{period}.xlsx"
