"""Reorganize the delivery into ingesta / procesamiento / salida + legacy.

Nothing is deleted. Files are *moved* by explicit rules, their SHA-256 is
verified at the destination, and ``datos/MAPA_MIGRACION.json`` records
every old -> new path so the change is reversible. Text references (TOML,
Python, JSON catalogs) are rewritten from the same map.

Usage (from the project root, the folder that holds ``icml-colombia``)::

    python tools/release/reorganize_layout.py --root .          # dry run
    python tools/release/reorganize_layout.py --root . --aplicar
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

INGESTA = "datos/1_ingesta"
PROC = "datos/2_procesamiento"
SALIDA = "datos/3_salida"
LEGACY = "legacy"
PARAMS = f"{PROC}/parametros_congelados"
FROZEN = f"{PROC}/productos_congelados"
PREPARED = f"{PROC}/fuentes_preparadas"

#: (pattern, destination directory). First match wins. ``dir/**`` keeps the
#: remainder of the path under the destination; any other pattern is matched
#: segment by segment and places the file name under the destination.
RULES: tuple[tuple[str, str], ...] = (
    # --- legacy: unused duplicates, past deliveries and RC1 references
    ("insumos/fuentes/archivo_original/**", f"{LEGACY}/archivo_original_duplicado"),
    # --- ingesta: Excel the user maintains
    ("insumos/fuentes/dane/**", f"{INGESTA}/dane"),
    ("insumos/fuentes/excel_originales/**", f"{INGESTA}/excel_originales"),
    ("insumos/censo_original/**", f"{INGESTA}/censo_original"),
    (
        "insumos/sectorial/anexos_historicos/*.xls",
        f"{INGESTA}/excel_originales/Mercado Laboral/Anexos sectoriales historicos",
    ),
    # --- procesamiento: prepared sources, frozen parameters and products
    ("insumos/sectorial/anexos_historicos/**", f"{PREPARED}/sectorial/anexos_historicos"),
    ("insumos/sectorial/**", f"{PREPARED}/sectorial"),
    ("insumos/fuentes/historicas/auditoria_h30/**", f"{PROC}/auditoria_historica_h30"),
    ("insumos/fuentes/historicas/**", PREPARED),
    ("insumos/fuentes/REGISTRO_EXCEL_ORIGINALES_H29.json", f"{PROC}/catalogos"),
    ("insumos/catalogo_fuentes.json", f"{PROC}/catalogos"),
    ("insumos/LEER_PRIMERO_INSUMOS.md", f"{PROC}/catalogos"),
    ("insumos/laboral/**", f"{FROZEN}/laboral"),
    ("insumos/informalidad/**", f"{PREPARED}/informalidad"),
    ("insumos/anclas_dane/**", f"{PREPARED}/anclas_dane"),
    ("insumos/demografia/**", f"{PREPARED}/demografia"),
    ("insumos/*.csv", f"{PREPARED}/censo_derivado"),
    ("censo/puente_v001/**", f"{PARAMS}/puente_censal_cnpv2018"),
    ("informalidad/census_transfer_v012/**", f"{PARAMS}/priors_mlp_h9"),
    ("informalidad/secuencia_v003/**", f"{PARAMS}/informalidad_secuencia_h5_h6"),
    ("informalidad/cierre_integral_v013/**", f"{PARAMS}/informalidad_cierre_h9"),
    ("informalidad/national_bridge_stress_v011/**", f"{PARAMS}/stress_puente_nacional"),
    ("CIERRE_MODELO/PRODUCTOS/**", f"{FROZEN}/sectorial"),
    ("_test_quality_run/products/**", f"{FROZEN}/pruebas_calidad"),
    ("CIERRE_OPERATIVO_H19/**", f"{FROZEN}/catalogo_h19"),
    ("research/sectoral/h16/**", f"{PROC}/sectorial_h16"),
    ("research/sectoral/h11/**", f"{PROC}/sectorial_h11"),
)

#: Folders and files that stay where they are.
KEEP_TOP = (
    "icml-colombia",
    "dependencias",
    "datos",
    "legacy",
    ".venv",
)
KEEP_ROOT_FILES_PREFIX = ("LEER_PRIMERO", "INSTALAR", "MANIFIESTO")

#: Folders with text references that must follow the files.
REWRITE_DIRS = (
    "icml-colombia/src",
    "icml-colombia/configs",
    "icml-colombia/tests",
    "icml-colombia/tools",
    "icml-colombia/scripts",
)
REWRITE_FILES = ("icml-colombia/README.md",)
#: Never rewritten: this tool states the old paths on purpose, and so does
#: its test.
REWRITE_EXCLUDE = frozenset(
    {
        "icml-colombia/tools/release/reorganize_layout.py",
        "icml-colombia/tests/unit/test_reorganize_layout.py",
    }
)
#: Moved data files whose *content* names project paths that code reads.
DATA_FILES_WITH_PATHS = (
    "catalogo_fuentes.json",
    "REGISTRO_EXCEL_ORIGINALES_H29.json",
    "19_catalogo_unificado.csv",
    "LEER_PRIMERO_INSUMOS.md",
)
REWRITE_SUFFIXES = {".py", ".toml", ".json", ".md", ".ps1", ".sh", ".bat", ".yml"}


@dataclass(frozen=True)
class Move:
    """One file to move."""

    source: str
    destination: str
    rule: str


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matches(pattern: str, relative: str) -> bool:
    if pattern.endswith("/**"):
        return relative.startswith(pattern[:-2])
    pattern_parts = pattern.split("/")
    parts = relative.split("/")
    return len(parts) == len(pattern_parts) and all(
        fnmatchcase(part, expected) for part, expected in zip(parts, pattern_parts, strict=True)
    )


def destination_for(relative: str) -> tuple[str, str] | None:
    """Return ``(destination path, rule)`` for a file, or ``None``."""
    for pattern, folder in RULES:
        if _matches(pattern, relative):
            if pattern.endswith("/**"):
                tail = relative[len(pattern) - 2 :]
            else:
                tail = PurePosixPath(relative).name
            return f"{folder}/{tail}", pattern
    return None


def _is_kept(relative: str) -> bool:
    parts = relative.split("/")
    if parts[0] in KEEP_TOP:
        return True
    return len(parts) == 1 and parts[0].startswith(KEEP_ROOT_FILES_PREFIX)


def build_plan(root: Path) -> tuple[list[Move], list[str]]:
    """Return the moves and the files that no rule covers."""
    moves: list[Move] = []
    unclassified: list[str] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".venv"}]
        for name in sorted(files):
            relative = Path(current, name).relative_to(root).as_posix()
            if _is_kept(relative):
                continue
            found = destination_for(relative)
            if found is None:
                unclassified.append(relative)
            else:
                moves.append(Move(relative, found[0], found[1]))
    return moves, unclassified


def check_plan(root: Path, moves: list[Move]) -> list[str]:
    """Return problems that would make the plan unsafe."""
    problems: list[str] = []
    counts = Counter(m.destination for m in moves)
    problems += [f"two files map to {d}" for d, n in counts.items() if n > 1]
    problems += [
        f"destination already exists: {m.destination}"
        for m in moves
        if (root / m.destination).exists()
    ]
    return problems


def _directory_prefixes(moves: list[Move]) -> list[tuple[str, str]]:
    """Directory-level replacements derived from the ``dir/**`` rules."""
    used = {m.rule for m in moves}
    pairs = []
    for pattern, folder in RULES:
        if pattern.endswith("/**") and pattern in used:
            old = pattern[:-3]
            pairs.append((old + "/", folder + "/"))
            # A directory written without its trailing slash, as in
            # ``root / "research/sectoral/h16"``.
            for quote in ('"', "'"):
                pairs.append((old + quote, folder + quote))
    return pairs


def _replace_path(text: str, old: str, replacement: str) -> tuple[str, int]:
    """Replace ``old`` only where it starts a path (idempotent).

    A new path may contain the old one as a suffix (``legacy/validacion``
    contains ``validacion``). Requiring that ``old`` is not preceded by a
    path character keeps repeated runs from stacking prefixes.
    """
    pattern = re.compile(r"(?<![\w/.\-])" + re.escape(old))
    return pattern.subn(lambda _: replacement, text)


def rewrite_references(root: Path, moves: list[Move]) -> dict[str, int]:
    """Rewrite old paths in text files; return the replacements per file."""
    file_pairs = sorted(((m.source, m.destination) for m in moves), key=lambda p: -len(p[0]))
    dir_pairs = sorted(_directory_prefixes(moves), key=lambda p: -len(p[0]))
    targets: list[Path] = [root / f for f in REWRITE_FILES if (root / f).is_file()]
    for folder in REWRITE_DIRS:
        base = root / folder
        if base.is_dir():
            targets += [
                p
                for p in base.rglob("*")
                if p.is_file() and p.suffix in REWRITE_SUFFIXES and "__pycache__" not in p.parts
            ]
    # JSON catalogs that the code reads by path.
    for move in moves:
        if move.destination.endswith(DATA_FILES_WITH_PATHS):
            targets.append(root / move.destination)
    changed: dict[str, int] = {}
    for path in dict.fromkeys(targets):
        if path.relative_to(root).as_posix() in REWRITE_EXCLUDE:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new, count = text, 0
        for old, replacement in (*file_pairs, *dir_pairs):
            new, hits = _replace_path(new, old, replacement)
            count += hits
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed[path.relative_to(root).as_posix()] = count
    return changed


def leftover_references(root: Path, moves: list[Move]) -> dict[str, list[str]]:
    """Find old folder names still written in code after the rewrite.

    A folder that was renamed (``secuencia_v003`` -> ``informalidad_...``)
    can survive inside a partial check such as ``rel.endswith('secuencia_v003/x.csv')``
    that no full-path replacement sees. Such a check silently stops matching,
    so every survivor is reported.
    """
    names: dict[str, str] = {}
    for pattern, folder in RULES:
        if pattern.endswith("/**"):
            old = pattern[:-3].rsplit("/", 1)[-1]
            if old != folder.rsplit("/", 1)[-1] and "_" in old and len(old) > 6:
                names[old] = folder
    used = {m.rule for m in moves}
    names = {o: f for o, f in names.items() if any(o in r for r in used)}
    found: dict[str, list[str]] = {}
    for folder in REWRITE_DIRS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            relative = path.relative_to(root).as_posix()
            if (
                not path.is_file()
                or path.suffix not in REWRITE_SUFFIXES
                or relative in REWRITE_EXCLUDE
                or "__pycache__" in path.parts
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for old in names:
                if re.search(r"(?<![\w])" + re.escape(old) + r"(?![\w])", text):
                    found.setdefault(relative, []).append(old)
    return found


def apply_plan(root: Path, moves: list[Move]) -> dict:
    """Move the files, verify hashes and write the migration map."""
    entries = []
    for move in moves:
        source = root / move.source
        target = root / move.destination
        digest = sha256_file(source)
        size = source.stat().st_size
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        if sha256_file(target) != digest:
            raise RuntimeError(f"Hash changed while moving {move.source}")
        entries.append(
            {
                "old": move.source,
                "new": move.destination,
                "sha256": digest,
                "bytes": size,
                "rule": move.rule,
            }
        )
    # Remove only directories that are now empty (never a file).
    for current, _, _ in sorted(os.walk(root), key=lambda x: -len(x[0])):
        path = Path(current)
        if path != root and ".venv" not in path.parts and not any(path.iterdir()):
            path.rmdir()
    (root / SALIDA).mkdir(parents=True, exist_ok=True)
    (root / SALIDA / "LEEME.txt").write_text(
        "Cada ejecucion crea aqui una carpeta AAAA-MM-DD_HHMMSS__corte-AAAA-MM__modo "
        "con universo_censo/ y universo_geih/.\n",
        encoding="utf-8",
    )
    migration = {
        "schema": "icml.layout_migration.v1",
        "files_moved": len(entries),
        "deleted": 0,
        "entries": entries,
    }
    (root / "datos" / "MAPA_MIGRACION.json").write_text(
        json.dumps(migration, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return migration


def moves_from_map(root: Path) -> list[Move]:
    """Rebuild the moves from ``datos/MAPA_MIGRACION.json``."""
    data = json.loads((root / "datos" / "MAPA_MIGRACION.json").read_text("utf-8"))
    return [Move(e["old"], e["new"], e["rule"]) for e in data["entries"]]


def main(argv: list[str] | None = None) -> int:
    """Run the reorganization (dry run unless ``--aplicar``)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--aplicar", action="store_true", help="Move the files.")
    parser.add_argument(
        "--reescribir",
        action="store_true",
        help="Only rewrite text references, from datos/MAPA_MIGRACION.json.",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.reescribir:
        moves = moves_from_map(root)
        changed = rewrite_references(root, moves)
        print(f"Rewrote {len(changed)} text files.")
        left = leftover_references(root, moves)
        for path, olds in sorted(left.items()):
            print(f"  REVIEW (old folder name still in code): {path}: {sorted(set(olds))}")
        return 3 if left else 0
    moves, unclassified = build_plan(root)
    problems = check_plan(root, moves)
    by_folder = Counter("/".join(m.destination.split("/")[:3]) for m in moves)
    print(f"{len(moves)} files to move; {len(unclassified)} unclassified; {len(problems)} problems")
    for item in unclassified:
        print("  UNCLASSIFIED:", item)
    for item in problems:
        print("  PROBLEM:", item)
    if unclassified or problems:
        return 2
    if not args.aplicar:
        for folder, count in sorted(by_folder.items()):
            print(f"  {count:4} -> {folder}")
        print("Dry run: nothing changed. Use --aplicar to move.")
        return 0
    migration = apply_plan(root, moves)
    changed = rewrite_references(root, moves)
    print(f"Moved {migration['files_moved']} files (deleted 0); rewrote {len(changed)} text files.")
    left = leftover_references(root, moves)
    for path, olds in sorted(left.items()):
        print(f"  REVIEW (old folder name still in code): {path}: {sorted(set(olds))}")
    return 3 if left else 0


if __name__ == "__main__":
    sys.exit(main())
