"""Give every DANE annex in ``datos/1_ingesta`` its canonical name and folder.

    geih_mercado_laboral/geih_mercado_laboral_AAAA-MM.xlsx
    geih_informalidad/geih_informalidad_AAAA-MM.xlsx
    geih_departamentos/geih_departamentos_AAAA.xlsx

The calculation does not depend on these names (the period is read from the
workbook and the name only classifies it), so this is for the user's clarity.
Nothing is deleted: identical copies move to ``legacy/ingesta_duplicados``,
hashes are verified after every move, and the paths written in code,
configurations and catalogs are rewritten from the same map.

    python rename_ingestion.py --root .            # dry run
    python rename_ingestion.py --root . --aplicar
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

from icml.ingestion.discovery import DEPARTMENTS, INFORMALITY, LABOR, classify

INGESTA = "datos/1_ingesta"
DUPLICATES = "legacy/ingesta_duplicados"
FOLDERS = {LABOR: "geih_mercado_laboral", INFORMALITY: "geih_informalidad", DEPARTMENTS: "geih_departamentos"}
CATALOGS = (
    "datos/2_procesamiento/catalogos/catalogo_fuentes.json",
    "datos/2_procesamiento/catalogos/REGISTRO_EXCEL_ORIGINALES_H29.json",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(kind: str, period: str, suffix: str) -> str:
    """Return the canonical relative path of an annex."""
    folder = FOLDERS[kind]
    return f"{INGESTA}/{folder}/geih_{kind}_{period}{suffix.lower()}"


def build_plan(root: Path) -> dict:
    """Return ``{moves, duplicates, rewrite}`` without touching anything."""
    claims: dict[str, list[Path]] = {}
    for path in sorted((root / INGESTA).rglob("*")):
        if path.is_file() and path.suffix.lower() in {".xlsx", ".xls"}:
            label = classify(path.name)
            if label:
                claims.setdefault(canonical(*label, path.suffix), []).append(path)
    moves, duplicates, rewrite = [], [], {}
    for destination, paths in sorted(claims.items()):
        if len({_sha(p) for p in paths}) > 1:
            raise ValueError(f"{destination}: different files claim it: {[str(p) for p in paths]}")
        # Keep the copy that already sits at the canonical place, else the first.
        paths.sort(key=lambda p: (p.relative_to(root).as_posix() != destination, str(p)))
        keeper, extra = paths[0], paths[1:]
        for path in paths:
            rewrite[path.relative_to(root).as_posix()] = destination
        if keeper.relative_to(root).as_posix() != destination:
            moves.append((keeper.relative_to(root).as_posix(), destination))
        for path in extra:
            relative = path.relative_to(root / INGESTA).as_posix()
            duplicates.append((path.relative_to(root).as_posix(), f"{DUPLICATES}/{relative}"))
    return {"moves": moves, "duplicates": duplicates, "rewrite": rewrite}


def _load_rewriter(root: Path):
    path = Path(__file__).with_name("reorganize_layout.py")
    spec = importlib.util.spec_from_file_location("reorganize_layout", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def apply_plan(root: Path, plan: dict) -> dict:
    """Move files (verifying hashes) and rewrite references."""
    done = []
    for source, destination in [*plan["moves"], *plan["duplicates"]]:
        origin, target = root / source, root / destination
        digest = _sha(origin)
        if target.exists():
            raise FileExistsError(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(origin), str(target))
        if _sha(target) != digest:
            raise RuntimeError(f"Hash changed while moving {source}")
        done.append({"old": source, "new": destination, "sha256": digest})
    layout = _load_rewriter(root)
    pairs = sorted(plan["rewrite"].items(), key=lambda item: -len(item[0]))
    targets = [root / f for f in layout.REWRITE_FILES if (root / f).is_file()]
    for folder in layout.REWRITE_DIRS:
        base = root / folder
        if base.is_dir():
            targets += [p for p in base.rglob("*") if p.is_file() and p.suffix in layout.REWRITE_SUFFIXES
                        and "__pycache__" not in p.parts]
    targets += [root / c for c in CATALOGS if (root / c).is_file()]
    changed = {}
    for path in dict.fromkeys(targets):
        relative = path.relative_to(root).as_posix()
        if relative in layout.REWRITE_EXCLUDE or relative.endswith("rename_ingestion.py"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new, count = text, 0
        for old, replacement in pairs:
            new, hits = layout._replace_path(new, old, replacement)
            count += hits
        if new != text:
            path.write_text(new, encoding="utf-8")
            changed[relative] = count
    map_path = root / "datos" / "MAPA_RENOMBRADO_INGESTA.json"
    map_path.write_text(json.dumps({"moved": done, "deleted": 0}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for current, _, _ in sorted(__import__("os").walk(root / INGESTA), key=lambda x: -len(x[0])):
        folder = Path(current)
        if folder != root / INGESTA and not any(folder.iterdir()):
            folder.rmdir()
    return {"moved": len(done), "rewritten_files": len(changed)}


def main(argv: list[str] | None = None) -> int:
    """Dry run unless ``--aplicar``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--aplicar", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    plan = build_plan(root)
    print(f"{len(plan['moves'])} renombrados, {len(plan['duplicates'])} copias idénticas a legacy, "
          f"{len(plan['rewrite'])} rutas a reescribir")
    for source, destination in plan["moves"]:
        print(f"  {source}\n      -> {destination}")
    for source, destination in plan["duplicates"]:
        print(f"  [duplicado] {source}\n      -> {destination}")
    if not args.aplicar:
        print("Simulacro: no se cambió nada. Use --aplicar.")
        return 0
    result = apply_plan(root, plan)
    print(f"Hecho: {result['moved']} archivos movidos, {result['rewritten_files']} archivos de texto reescritos (borrados: 0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
