#!/usr/bin/env bash
# Shortcut to run ICML without activating the environment:
#   ./icml.sh status        ./icml.sh rebuild        ./icml.sh update        ./icml.sh plots
cd "$(dirname "$0")" || exit 1
if [ ! -x ".venv/bin/python" ]; then
  echo "The environment is missing. Run first:  ./install.sh" >&2
  exit 1
fi
exec .venv/bin/python -m icml "$@"
