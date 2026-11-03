@echo off
REM Uso: run_integral_agosto.bat "RAIZ_ICML" "SALIDA_NUEVA" [verify^|recompute-components^|recompute] [FUENTES]
set "MODE=%~3"
if "%MODE%"=="" set "MODE=verify"
if "%~4"=="" (
    python -m icml operations run-integral --root "%~1" --output "%~2" --mode "%MODE%"
) else (
    python -m icml operations run-integral --root "%~1" --output "%~2" --mode "%MODE%" --sources "%~4"
)
exit /b %ERRORLEVEL%
