# Script para levantar Frontend + Backend simultáneamente
# Uso: .\START_ESTIMASTRUCT.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON = "python"
$BACKEND_PATH = Join-Path $ROOT "backend"
$FRONTEND_PATH = Join-Path $ROOT "ESTIMASTRUCT"
$env:ESTIMASTRUCT_API_BASE = "http://localhost:8002"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ESTIMASTRUCT — Iniciando Servidores" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Matar procesos existentes en puertos 5000 y 8002
Write-Host "🔍 Limpiando puertos..." -ForegroundColor Yellow
$procs = netstat -ano | findstr ":5000 " | findstr LISTENING
if ($procs) {
    $pid = $procs -split '\s+' | Select-Object -Last 1
    Write-Host "  • Matando proceso en puerto 5000 (PID $pid)"
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
}

$procs = netstat -ano | findstr ":8002 " | findstr LISTENING
if ($procs) {
    $pid = $procs -split '\s+' | Select-Object -Last 1
    Write-Host "  • Matando proceso en puerto 8002 (PID $pid)"
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1
Write-Host ""

# Instalar dependencias
Write-Host "📦 Instalando dependencias..." -ForegroundColor Yellow
& $PYTHON -m pip install -r (Join-Path $ROOT "backend\requirements.txt") -q 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Dependencias instaladas" -ForegroundColor Green
} else {
    Write-Host "  ✗ Error instalando dependencias" -ForegroundColor Red
}
Write-Host ""

# Funciones para logging con color
function LogBackend {
    param([string]$msg)
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] [BACKEND:8002]  $msg" -ForegroundColor Magenta
}

function LogFrontend {
    param([string]$msg)
    Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] [FRONTEND:5000] $msg" -ForegroundColor Cyan
}

# Iniciar Backend FastAPI (puerto 8002)
Write-Host "🚀 Iniciando Backend FastAPI en puerto 8002..." -ForegroundColor Green
$backendJob = Start-Job -ScriptBlock {
    param($python, $path)
    Set-Location $path
    & $python -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload 2>&1
} -ArgumentList $PYTHON, $BACKEND_PATH

# Iniciar Frontend Flask (puerto 5000)
Write-Host "🚀 Iniciando Frontend Flask en puerto 5000..." -ForegroundColor Green
$frontendJob = Start-Job -ScriptBlock {
    param($python, $path)
    Set-Location $path
    & $python app.py 2>&1
} -ArgumentList $PYTHON, $FRONTEND_PATH

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "✓ Servidores iniciados" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Acceso:" -ForegroundColor Cyan
Write-Host "  Frontend:  http://localhost:5000/" -ForegroundColor White
Write-Host "  Backend:   http://localhost:8002/" -ForegroundColor White
Write-Host ""
Write-Host "Logs en vivo:" -ForegroundColor Cyan
Write-Host ""

# Mostrar logs en tiempo real
while ($true) {
    # Backend logs
    $backendOutput = Receive-Job -Job $backendJob -ErrorAction SilentlyContinue
    if ($backendOutput) {
        $backendOutput | ForEach-Object {
            if ($_ -match "error|ERROR|failed|FAILED") {
                Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] [BACKEND:8002]  $_" -ForegroundColor Red
            } else {
                Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] [BACKEND:8002]  $_" -ForegroundColor Magenta
            }
        }
    }

    # Frontend logs
    $frontendOutput = Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue
    if ($frontendOutput) {
        $frontendOutput | ForEach-Object {
            if ($_ -match "error|ERROR|failed|FAILED") {
                Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] [FRONTEND:5000] $_" -ForegroundColor Red
            } else {
                Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] [FRONTEND:5000] $_" -ForegroundColor Cyan
            }
        }
    }

    # Revisar si los jobs aún están corriendo
    if ($backendJob.State -ne "Running" -or $frontendJob.State -ne "Running") {
        Write-Host ""
        Write-Host "⚠ Servidor detenido. Presiona Ctrl+C para salir." -ForegroundColor Red
        Start-Sleep -Seconds 5
    }

    Start-Sleep -Milliseconds 500
}

# Limpiar al salir
Stop-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
Remove-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
