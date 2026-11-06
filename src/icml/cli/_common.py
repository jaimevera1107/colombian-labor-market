"""Helpers shared by the command modules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

EXIT_OK = 0
#: A user mistake (wrong folder, malformed month, ...) printed as a plain message.
EXIT_ERROR = 1
#: The command finished, but an integrity gate or audit did not pass, or the
#: user has to act before anything can be computed.
EXIT_INTEGRITY_FAILURE = 2
EXIT_ACTION = EXIT_INTEGRITY_FAILURE

if TYPE_CHECKING:
    Commands = argparse._SubParsersAction[argparse.ArgumentParser]
else:  # pragma: no cover - alias for annotations only
    Commands = argparse._SubParsersAction


def print_json(payload: Any) -> None:
    """Print a JSON report the way every expert command does."""
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def write_new_report(path: Path | None, payload: Any) -> None:
    """Write ``payload`` to a NEW JSON file; an existing file is never overwritten."""
    if path is None:
        return
    if path.exists():
        raise FileExistsError(f"Report already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def add_path_flags(parser: argparse.ArgumentParser, *names: str, required: bool = True) -> None:
    """Add ``--name`` options of type ``Path`` for every name given."""
    for name in names:
        parser.add_argument(f"--{name}", type=Path, required=required)
