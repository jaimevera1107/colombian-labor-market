@echo off
rem Create the ICML environment and install the package like any library (dependencies from PyPI).
rem Requires Python 3.11 or later. For the exact environment the reference vintage was frozen with,
rem run:  install.bat --locked   (Python 3.12, versions pinned in requirements\lock-py312.txt).
cd /d "%~dp0"

set PYEXE=
for %%V in (3.12 3.13 3.11 3.14) do (
    if not defined PYEXE (
        py -%%V --version >nul 2>&1 && set PYEXE=py -%%V
    )
)
if not defined PYEXE (
    python --version >nul 2>&1 && set PYEXE=python
)
if not defined PYEXE (
    echo ERROR: Python 3.11 or later was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add to PATH".
    exit /b 1
)
echo Using: %PYEXE%
%PYEXE% -m venv .venv || exit /b 1
.venv\Scripts\python -m pip install -U pip || exit /b 1
if "%~1"=="--locked" (
    .venv\Scripts\python -m pip install -r requirements\lock-py312.txt || exit /b 1
    .venv\Scripts\python -m pip install --no-deps -e . || exit /b 1
) else (
    .venv\Scripts\python -m pip install -e ".[dev]" || exit /b 1
)
rem Optional: torch for the informality MLP experiments:  .venv\Scripts\python -m pip install -e ".[ml]"
echo Environment ready. See README.md
