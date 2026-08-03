# EstimaStruct - wrapper local para levantar la app contra PostgreSQL primario
# sin romper la UI ni perder compatibilidad de export/import SQLite.

$ErrorActionPreference = 'Stop'
try { $PSNativeCommandUseErrorActionPreference = $false } catch {}
$Project = $PSScriptRoot
$RepoRoot = Split-Path $Project -Parent
$SecretFile = 'D:\Secrets\postgres_credentials.txt'

Write-Host "→ Sincronizando con origin/main..." -ForegroundColor Cyan
Push-Location $RepoRoot
git pull origin main --ff-only 2>&1 | Write-Host
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
