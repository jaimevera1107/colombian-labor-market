"""Check that a copy of the repository is complete and intact, or write its hash list.

``SHA256SUMS`` (repository root) lists every versioned file with its SHA-256,
in the format ``sha256sum -c`` reads. Because the data hashes depend on the
exact bytes, the repository disables line-ending conversion
(``.gitattributes``).

Generated outputs (the published base, the deliveries, the scratch space of
each run and the audit figures) are not versioned and are therefore never
listed: a listing written on a machine that has run the pipeline must equal
one written on a clean clone.

    icml checksums            # verify the copy against SHA256SUMS
    icml checksums --write    # regenerate SHA256SUMS (before a commit)
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from icml.layout import CURRENT_DIR, FROZEN_PRODUCTS_DIR, OUTPUT_DIR, RUNS_DIR

LISTING = "SHA256SUMS"
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "htmlcov", "build", "dist"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", LISTING}
#: Folders whose contents the pipeline generates; only a ``.gitkeep`` or a
#: ``LEEME`` placed there by hand is versioned.
GENERATED = (RUNS_DIR, CURRENT_DIR, OUTPUT_DIR, f"{FROZEN_PRODUCTS_DIR}/graficas_auditoria")
KEPT_PLACEHOLDERS = {".gitkeep", "LEEME.txt", "LEEME.md", "README.md"}


def _skipped(relative: Path) -> bool:
    parts = relative.parts
    if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in parts):
        return True
    if relative.name in SKIP_NAMES or relative.name.startswith("~$") or relative.suffix == ".pyc":
        return True
    posix = relative.as_posix()
    for folder in GENERATED:
        if posix.startswith(folder + "/"):
            inside = posix[len(folder) + 1:]
            return not ("/" not in inside and inside in KEPT_PLACEHOLDERS)
    return False


def tracked_files(root: Path) -> list[Path]:
    """Every file the repository versions, as paths relative to ``root``, sorted."""
    return sorted(
        p.relative_to(root)
        for p in Path(root).rglob("*")
        if p.is_file() and not _skipped(p.relative_to(root))
    )


def sha256(path: Path) -> str:
    """SHA-256 of a file, read in 1 MiB chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_listing(root: Path) -> int:
    """Write ``SHA256SUMS`` and return the number of files listed."""
    files = tracked_files(root)
    lines = [f"{sha256(root / p)}  {p.as_posix()}" for p in files]
    (root / LISTING).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(files)


def verify(root: Path) -> dict:
    """Compare the copy with ``SHA256SUMS``: missing, altered and extra files."""
    listing = Path(root) / LISTING
    if not listing.is_file():
        raise FileNotFoundError(f"{LISTING} not found in {root}")
    expected: dict[str, str] = {}
    for line in listing.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, _, name = line.partition("  ")
            expected[name] = digest
    present = {p.as_posix() for p in tracked_files(root)}
    missing = sorted(set(expected) - present)
    altered = sorted(n for n in set(expected) & present if sha256(root / n) != expected[n])
    extra = sorted(present - set(expected))
    return {"listed": len(expected), "missing": missing, "altered": altered, "extra": extra,
            "complete": not missing and not altered}
