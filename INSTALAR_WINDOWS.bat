@echo off
rem Crea el entorno del ICML con las versiones fijadas (reproducible).
cd /d "%~dp0"
py -3.12 -m venv .venv || exit /b 1
.venv\Scripts\python -m pip install -U pip setuptools wheel || exit /b 1
.venv\Scripts\python -m pip install --no-deps .\dependencias\tempdisagg-0.6.3-py3-none-any.whl || exit /b 1
.venv\Scripts\python -m pip install -r icml-colombia\requirements\lock-py312.txt || exit /b 1
.venv\Scripts\python -m pip install --no-deps -e .\icml-colombia || exit /b 1
rem Opcional: torch para las pruebas del modelo de informalidad (MLP).
rem   .venv\Scripts\python -m pip install -r icml-colombia\requirements\lock-py312-ml.txt
echo Entorno listo. Revise README.md
