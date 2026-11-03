"""Build the project root of an earlier monthly cutoff (command line wrapper).

    ICML_CUTOFF=2026-07 python build_vintage_root.py --root . --cutoff 2026-07 --workdir ../raiz_julio

The logic lives in ``icml.recalculation.vintage_root`` (it is what ``icml consolidar --hasta`` uses).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from icml.recalculation.vintage_root import build_vintage_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--cutoff", required=True)
    parser.add_argument("--workdir", type=Path, required=True, help="New folder")
    args = parser.parse_args(argv)
    try:
        build_vintage_root(args.root, args.cutoff, args.workdir)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    sys.exit(main())
