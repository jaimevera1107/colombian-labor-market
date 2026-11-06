@echo off
rem Shortcut to run ICML without activating the environment:
rem   icml status     icml rebuild     icml update     icml plots
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo The environment is missing. Run first: install.bat
  exit /b 1
)
".venv\Scripts\python.exe" -m icml %*
