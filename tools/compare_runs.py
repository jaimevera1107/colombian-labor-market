"""Compare the outputs of two full runs (deliveries and published base) modulo volatile fields.

Used to prove that a software change leaves the numbers untouched: run
``icml rebuild`` + ``icml update`` on two checkouts, then

    python tools/compare_runs.py <datos-of-checkout-A> <datos-of-checkout-B> [--root-a PATH --root-b PATH]

``--root-a``/``--root-b`` name the checkout roots recorded inside the
manifests when they are not the parents of the ``datos`` folders given
(copies of the outputs, for instance).

Deliveries are paired by their name without the timestamp. CSV files must be
byte-identical. JSON manifests are compared after dropping run ids,
timestamps, the software version and the absolute path of the checkout.
XLSX files are compared member by member, ignoring ``docProps/core.xml``
(openpyxl writes the creation time there). Exit code 1 on any difference.
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}_\d{6}")
VOLATILE = {"run_id", "created_at_bogota", "created_at_utc", "software_version"}


def _normalize(value, roots: tuple[str, ...]):
    if isinstance(value, dict):
        return {k: _normalize(v, roots) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        items = [_normalize(v, roots) for v in value]
        return sorted(items, key=json.dumps) if all(isinstance(v, str) for v in items) else items
    if isinstance(value, str):
        text = TIMESTAMP.sub("TS", value)
        for root in roots:
            text = text.replace(root, "<ROOT>")
        return re.sub(r"/tmp/icml_integral_[^/]+", "/tmp/icml_integral_X", text)
    return value


def _json_diff(a, b, path: str = "", out: list[str] | None = None) -> list[str]:
    out = [] if out is None else out
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append(f"{path}/{key}: only in {'B' if key not in a else 'A'}")
            else:
                _json_diff(a[key], b[key], f"{path}/{key}", out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            _json_diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: {str(a)[:60]!r} != {str(b)[:60]!r}")
    return out


def _xlsx_equal(a: Path, b: Path) -> bool:
    with zipfile.ZipFile(a) as za, zipfile.ZipFile(b) as zb:
        if za.namelist() != zb.namelist():
            return False
        return all(za.read(n) == zb.read(n) for n in za.namelist() if n != "docProps/core.xml")


def compare(datos_a: Path, datos_b: Path, root_a: Path | None = None, root_b: Path | None = None) -> list[str]:
    """Return a list of differences; empty means the two runs are equivalent."""
    roots = (str((root_a or datos_a.parent).resolve()), str((root_b or datos_b.parent).resolve()))
    trees = [(datos_a / "3_salida", datos_b / "3_salida"), (datos_a / "2_procesamiento/vigente", datos_b / "2_procesamiento/vigente")]
    problems: list[str] = []
    for ta, tb in trees:
        fa = {TIMESTAMP.sub("TS", str(p.relative_to(ta))): p for p in ta.rglob("*") if p.is_file()}
        fb = {TIMESTAMP.sub("TS", str(p.relative_to(tb))): p for p in tb.rglob("*") if p.is_file()}
        problems += [f"missing in B: {k}" for k in sorted(set(fa) - set(fb))]
        problems += [f"missing in A: {k}" for k in sorted(set(fb) - set(fa))]
        for key in sorted(set(fa) & set(fb)):
            if key in ("LEEME.txt", ".gitkeep"):
                continue  # versioned placeholders, not outputs
            a, b = fa[key], fb[key]
            raw_a, raw_b = a.read_bytes(), b.read_bytes()
            if raw_a == raw_b:
                continue
            if key.endswith(".json"):
                details = _json_diff(_normalize(json.loads(raw_a), roots), _normalize(json.loads(raw_b), roots))
                if details:
                    problems.append(f"json differs: {key}")
                    problems += [f"    {d}" for d in details[:8]]
            elif key.endswith(".xlsx"):
                if not _xlsx_equal(a, b):
                    problems.append(f"xlsx differs: {key}")
            elif key.endswith((".csv", ".txt", ".md")):
                if TIMESTAMP.sub("TS", raw_a.decode("utf-8", "replace")) != TIMESTAMP.sub("TS", raw_b.decode("utf-8", "replace")):
                    problems.append(f"text differs: {key}")
            else:
                problems.append(f"binary differs: {key}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("datos_a", type=Path)
    parser.add_argument("datos_b", type=Path)
    parser.add_argument("--root-a", type=Path)
    parser.add_argument("--root-b", type=Path)
    args = parser.parse_args(argv)
    problems = compare(args.datos_a, args.datos_b, args.root_a, args.root_b)
    print("\n".join(problems) if problems else "EQUIVALENT: no differences beyond run ids, timestamps and checkout paths")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
