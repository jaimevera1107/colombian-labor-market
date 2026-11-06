param([string]$Raiz="..", [string]$Salida="..\\auditorias\\control_h20")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\\..")
python -m icml operations preflight --root $Raiz --output (Join-Path $Salida "preflight")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m icml operations verify-products --root $Raiz --report (Join-Path $Salida "productos.json")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pytest -q tests/unit tests/regression
exit $LASTEXITCODE
