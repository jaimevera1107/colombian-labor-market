"""Command-line interface: ``icml <command>``.

Everyday commands (see ``icml --help``):

* ``icml status``   what the project holds and what to do next;
* ``icml rebuild``  recompute every year from 1993 and publish the base;
* ``icml update``   add the new month, keeping the anchored years frozen;
* ``icml plots``    draw the latest delivery;
* ``icml verify``   audit a delivery.

Expert commands drive single stages, research experiments and the
operational gates: ``run``, ``<stage> run``, ``informality``, ``sectoral``,
``census-bridge``, ``operations``, ``delivery``, ``recalc`` and ``golden``.

Each command group lives in its own module and registers a parser with a
``handler`` default; ``main`` only parses and dispatches.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from icml import __version__
from icml.cli import delivery, operations, pipeline, project, sectoral
from icml.cli._common import EXIT_ERROR, EXIT_INTEGRITY_FAILURE, EXIT_OK

__all__ = ["EXIT_ERROR", "EXIT_INTEGRITY_FAILURE", "EXIT_OK", "build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    """Build the full ``icml`` parser with every command group registered."""
    parser = argparse.ArgumentParser(
        prog="icml",
        description="ICML: reconstruction and monthly update of Colombian labor-market series.",
        epilog="Everyday use: status, rebuild, update, plots, verify. The other commands are expert tools.",
    )
    parser.add_argument("--version", action="version", version=f"icml {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    project.register(commands)
    delivery.register(commands)
    pipeline.register(commands)
    sectoral.register(commands)
    operations.register(commands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = build_parser().parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:  # pragma: no cover - argparse enforces a subcommand
        build_parser().print_help()
        return EXIT_ERROR
    return int(handler(args))
