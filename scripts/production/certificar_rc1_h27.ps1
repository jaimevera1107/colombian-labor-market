# Certificacion de regresion RC1 (solo en Windows con Python 3.12)
# Ejecutar desde la raiz de icml-colombia; no modifica datos del ICML.
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path '.').Path
$Golden = (Resolve-Path '..\validacion\rc1_original').Path
$EnvDir = Join-Path $Root '.venv-rc1'
py -3.12 -m venv $EnvDir
if ($LASTEXITCODE -ne 0) { throw 'Se requiere Python 3.12' }
$Python = Join-Path $EnvDir 'Scripts\python.exe'
& $Python -m pip install -c requirements/lock-py312.txt -e '.[dev]'
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar el entorno bloqueado RC1' }
$env:ICML_GOLDEN_DIR = $Golden
& $Python -m pytest -q tests/regression
if ($LASTEXITCODE -ne 0) { throw 'RC1 NO certificado: existen pruebas de regresion fallidas' }
Write-Output 'La suite RC1 termino sin fallos. Conservar el log y las versiones exactas del entorno.'
