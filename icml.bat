@echo off
rem Atajo para usar el ICML sin activar el entorno:
rem   icml estado     icml consolidar --desde-cero     icml actualizar     icml graficos
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Falta el entorno. Ejecute primero: INSTALAR_WINDOWS.bat
  exit /b 1
)
".venv\Scripts\python.exe" -m icml %*
