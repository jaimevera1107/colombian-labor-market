#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
root="${1:-..}"
out="${2:-../auditorias/control_h20}"
python -m icml operations preflight --root "$root" --output "$out/preflight"
python -m icml operations verify-products --root "$root" --report "$out/productos.json"
python -m pytest -q tests/unit tests/regression
