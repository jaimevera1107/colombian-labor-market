@echo off
rem Crea el entorno del ICML con las versiones fijadas (reproducible).
rem Requiere Python 3.11, 3.12 o 3.13 instalado y en PATH.
cd /d "%~dp0"

rem Intentar py -3.12, luego -3.13, luego -3.11, luego python generico
set PYEXE=
for %%V in (3.12 3.13 3.14 3.11) do (
    if not defined PYEXE (
        py -%%V --version >nul 2>&1 && set PYEXE=py -%%V
    )
)
if not defined PYEXE (
    python --version >nul 2>&1 && set PYEXE=python
)
if not defined PYEXE (
    echo ERROR: No se encontro Python 3.11, 3.12 ni 3.13.
    echo Instalalo desde https://www.python.org/downloads/ y marca "Add to PATH".
    exit /b 1
)
echo Usando: %PYEXE%
%PYEXE% -m venv .venv || exit /b 1
.venv\Scripts\python -m pip install -U pip setuptools wheel || exit /b 1
.venv\Scripts\python -m pip install --no-deps .\dependencias\tempdisagg-0.6.3-py3-none-any.whl || exit /b 1
.venv\Scripts\python -m pip install -r requirements\lock-py312.txt || exit /b 1
.venv\Scripts\python -m pip install --no-deps -e . || exit /b 1
rem Opcional: torch para las pruebas del modelo de informalidad (MLP).
rem   .venv\Scripts\python -m pip install -r requirements\lock-py312-ml.txt
echo Entorno listo. Revise README.md
