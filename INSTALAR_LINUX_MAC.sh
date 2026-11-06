#!/usr/bin/env bash
# Crea el entorno del ICML con las versiones fijadas (reproducible).
# Requiere Python 3.11, 3.12 o 3.13.
set -euo pipefail
cd "$(dirname "$0")"

PYEXE=""
for V in python3.12 python3.13 python3.14 python3.11 python3; do
    if command -v "$V" >/dev/null 2>&1; then
        PYEXE="$V"; break
    fi
done
if [ -z "$PYEXE" ]; then
    echo "ERROR: No se encontró Python 3.11, 3.12 ni 3.13." >&2
    echo "Instálalo desde https://www.python.org/downloads/" >&2
    exit 1
fi
echo "Usando: $PYEXE ($($PYEXE --version))"
"$PYEXE" -m venv .venv
.venv/bin/python -m pip install -U pip setuptools wheel
.venv/bin/python -m pip install --no-deps ./dependencias/tempdisagg-0.6.3-py3-none-any.whl
.venv/bin/python -m pip install -r requirements/lock-py312.txt
.venv/bin/python -m pip install --no-deps -e .
# Opcional: torch para las pruebas del modelo de informalidad (MLP).
#   .venv/bin/python -m pip install -r requirements/lock-py312-ml.txt
printf 'Entorno listo. Revise README.md\n'
