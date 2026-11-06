param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Output,
    [ValidateSet('verify','recompute-components','recompute')][string]$Mode='verify',
    [string]$Sources=''
)
$ErrorActionPreference = 'Stop'
$argv = @('-m','icml','operations','run-integral','--root',$Root,'--mode',$Mode,'--output',$Output)
if ($Sources) { $argv += @('--sources',$Sources) }
& python @argv
if ($LASTEXITCODE -ne 0) { throw "ICML H24: verificación o ejecución bloqueada (exit=$LASTEXITCODE). Consulte el JSON de auditoría." }
