"""Check that a copy of the repository is complete and intact, or write its hash list.

``SHA256SUMS`` (repository root) lists every tracked file with its SHA-256, in the
format ``sha256sum -c`` reads. Because the data hashes depend on the exact bytes,
the repository disables line-ending conversion (``.gitattributes``).

    python verify_checkout.py              # verify the copy against SHA256SUMS
    python verify_checkout.py --escribir   # regenerate SHA256SUMS (before a commit)
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

LISTING = "SHA256SUMS"
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "htmlcov", "build", "dist"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", LISTING}
TEMPORARY = "datos/2_procesamiento/_corridas"


def _skipped(relative: Path) -> bool:
    parts = relative.parts
    if any(part in SKIP_DIRS or part.endswith(".egg-info") for part in parts):
        return True
    if relative.name in SKIP_NAMES or relative.name.startswith("~$") or relative.suffix == ".pyc":
        return True
    return relative.as_posix().startswith(TEMPORARY + "/") and relative.name != ".gitkeep"


def tracked_files(root: Path) -> list[Path]:
    """Every file the repository versions, as paths relative to ``root``, sorted."""
    return sorted(
        p.relative_to(root)
        for p in Path(root).rglob("*")
        if p.is_file() and not _skipped(p.relative_to(root))
    )


def sha256(path: Path) -> str:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parents[3], help="Repository root")
    parser.add_argument("--escribir", action="store_true", help="Regenerate SHA256SUMS")
    parser.add_argument("--estricto", action="store_true", help="Also fail on files not in the list")
    args = parser.parse_args(argv)
    root = args.raiz.resolve()
    if args.escribir:
        print(f"{LISTING}: {write_listing(root)} archivos")
        return 0
    result = verify(root)
    for label, key in (("FALTA", "missing"), ("ALTERADO", "altered"), ("NO LISTADO", "extra")):
        for name in result[key][:20]:
            print(f"{label}: {name}")
        if len(result[key]) > 20:
            print(f"  ... y {len(result[key]) - 20} más")
    ok = result["complete"] and not (args.estricto and result["extra"])
    print(f"{'COMPLETA E INTACTA' if ok else 'INCOMPLETA O ALTERADA'}: {result['listed']} archivos listados, "
          f"{len(result['missing'])} faltan, {len(result['altered'])} alterados, {len(result['extra'])} no listados")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
