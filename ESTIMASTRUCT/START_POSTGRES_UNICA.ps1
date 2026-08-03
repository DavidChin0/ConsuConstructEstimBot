# EstimaStruct - wrapper local para levantar la app contra PostgreSQL primario
# sin romper la UI ni perder compatibilidad de export/import SQLite.

$ErrorActionPreference = 'Stop'
$Project = $PSScriptRoot
$RepoRoot = Split-Path $Project -Parent
$SecretFile = 'D:\Secrets\postgres_credentials.txt'

Write-Host "→ Sincronizando con origin/main..." -ForegroundColor Cyan
Push-Location $RepoRoot
# git escribe su output normal ("From https://...") a stderr. En PowerShell 5.1,
# $PSNativeCommandUseErrorActionPreference no existe (recien en 7.3+) -- con
# ErrorActionPreference=Stop, ese stderr se promueve a excepcion terminante y
# aborta el script sin avisar (bug real encontrado 2026-08-02, goal-20190/20192:
# el "fix" anterior con esa variable era un placebo en 5.1). Fix real,
# version-agnostico: bajar a Continue solo para este native call.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
git pull origin main --ff-only 2>&1 | Write-Host
$ErrorActionPreference = $prevEAP
Pop-Location


if (-not (Test-Path $SecretFile)) {
  throw "No existe $SecretFile. Crea el archivo de credenciales o exporta ESTIMASTRUCT_DATABASE_URL manualmente."
}

$password = (
  Get-Content $SecretFile |
  Where-Object { $_ -match '^password=' } |
  Select-Object -First 1
)

if (-not $password) {
  throw "No se encontró una línea password=... en $SecretFile"
}

$password = $password.Substring(9)
$env:ESTIMASTRUCT_DATABASE_URL = "postgresql+psycopg://postgres:$password@127.0.0.1:5432/estimastruct"
$env:ESTIMASTRUCT_AUTO_CREATE_SCHEMA = 'false'
$env:ESTIMASTRUCT_CANONICAL_ROOT = $Project

& (Join-Path $Project 'START_UNICA.ps1')
