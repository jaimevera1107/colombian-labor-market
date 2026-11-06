#!/usr/bin/env bash
# Create the ICML environment with the pinned versions (reproducible).
# Requires Python 3.11, 3.12 or 3.13.
set -euo pipefail
cd "$(dirname "$0")"

PYEXE=""
for V in python3.12 python3.13 python3.14 python3.11 python3; do
    if command -v "$V" >/dev/null 2>&1; then
        PYEXE="$V"; break
    fi
done
if [ -z "$PYEXE" ]; then
    echo "ERROR: Python 3.11, 3.12 or 3.13 was not found." >&2
    echo "Install it from https://www.python.org/downloads/" >&2
    exit 1
fi
echo "Using: $PYEXE ($($PYEXE --version))"
"$PYEXE" -m venv .venv
.venv/bin/python -m pip install -U pip setuptools wheel
.venv/bin/python -m pip install --no-deps ./vendor/tempdisagg-0.6.3-py3-none-any.whl
.venv/bin/python -m pip install -r requirements/lock-py312.txt
.venv/bin/python -m pip install --no-deps -e .
# Optional: torch for the informality MLP experiments.
#   .venv/bin/python -m pip install -r requirements/lock-py312-ml.txt
printf 'Environment ready. See README.md\n'
