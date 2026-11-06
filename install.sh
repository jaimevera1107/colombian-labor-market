#!/usr/bin/env bash
# Create the ICML environment and install the package like any library (dependencies from PyPI).
# Requires Python 3.11 or later. For the exact environment the reference vintage was frozen with,
# run:  ./install.sh --locked   (Python 3.12, versions pinned in requirements/lock-py312.txt).
set -euo pipefail
cd "$(dirname "$0")"

PYEXE=""
for V in python3.12 python3.13 python3.11 python3.14 python3; do
    if command -v "$V" >/dev/null 2>&1; then
        PYEXE="$V"; break
    fi
done
if [ -z "$PYEXE" ]; then
    echo "ERROR: Python 3.11 or later was not found." >&2
    echo "Install it from https://www.python.org/downloads/" >&2
    exit 1
fi
echo "Using: $PYEXE ($($PYEXE --version))"
"$PYEXE" -m venv .venv
.venv/bin/python -m pip install -U pip
if [ "${1:-}" = "--locked" ]; then
    .venv/bin/python -m pip install -r requirements/lock-py312.txt
    .venv/bin/python -m pip install --no-deps -e .
else
    .venv/bin/python -m pip install -e ".[dev]"
fi
# Optional: torch for the informality MLP experiments:  .venv/bin/python -m pip install -e ".[ml]"
printf 'Environment ready. See README.md\n'
