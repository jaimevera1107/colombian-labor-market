#!/usr/bin/env bash
# Crea el entorno del ICML con las versiones fijadas (reproducible).
set -euo pipefail
cd "$(dirname "$0")"
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip setuptools wheel
.venv/bin/python -m pip install --no-deps ./dependencias/tempdisagg-0.6.3-py3-none-any.whl
.venv/bin/python -m pip install -r icml-colombia/requirements/lock-py312.txt
.venv/bin/python -m pip install --no-deps -e ./icml-colombia
# Opcional: torch para las pruebas del modelo de informalidad (MLP).
#   .venv/bin/python -m pip install -r icml-colombia/requirements/lock-py312-ml.txt
printf 'Entorno listo. Revise README.md\n'
