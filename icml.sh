#!/usr/bin/env bash
# Atajo para usar el ICML sin activar el entorno:
#   ./icml.sh estado        ./icml.sh consolidar --desde-cero        ./icml.sh actualizar        ./icml.sh graficos
cd "$(dirname "$0")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "Falta el entorno. Ejecute primero:  ./INSTALAR_LINUX_MAC.sh" >&2
  exit 1
fi
exec .venv/bin/python -m icml "$@"
