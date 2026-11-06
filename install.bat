@echo off
rem Create the ICML environment with the pinned versions (reproducible).
rem Requires Python 3.11, 3.12 or 3.13 installed and on PATH.
cd /d "%~dp0"

rem Try py -3.12, then -3.13, then -3.11, then a generic python
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
    echo ERROR: Python 3.11, 3.12 or 3.13 was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add to PATH".
    exit /b 1
)
echo Using: %PYEXE%
%PYEXE% -m venv .venv || exit /b 1
.venv\Scripts\python -m pip install -U pip setuptools wheel || exit /b 1
.venv\Scripts\python -m pip install --no-deps .\vendor\tempdisagg-0.6.3-py3-none-any.whl || exit /b 1
.venv\Scripts\python -m pip install -r requirements\lock-py312.txt || exit /b 1
.venv\Scripts\python -m pip install --no-deps -e . || exit /b 1
rem Optional: torch for the informality MLP experiments.
rem   .venv\Scripts\python -m pip install -r requirements\lock-py312-ml.txt
echo Environment ready. See README.md
