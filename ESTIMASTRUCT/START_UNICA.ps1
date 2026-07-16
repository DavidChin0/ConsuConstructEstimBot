# EstimaStruct - lanzador en UNA sola ventana (backend 8002 + frontend 5000)
# Salida ordenada: [BACK ] magenta, [FRONT] cyan. Cerrar la ventana detiene todo.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$Host.UI.RawUI.WindowTitle = 'EstimaStruct'

$PY       = 'D:\LLM\python\python.exe'
$PROJECT  = $PSScriptRoot   # portable: el lanzador vive en la raiz del repo
$API      = 'http://localhost:8002'

# Para el boton "Publicar a Portal": pega aca tu Supabase secret key (sb_secret_...).
# NO subir a git. Dejalo vacio si no vas a publicar.
$SUPABASE_SECRET_KEY = $env:SUPABASE_SECRET_KEY
# $SUPABASE_SECRET_KEY = 'sb_secret_xxxxxxxxxxxx'

function Kill-Port([int]$p) {
  $hits = netstat -ano | Select-String (":{0}\s" -f $p) | Select-String 'LISTENING'
  foreach ($h in $hits) {
    $procId = ($h.ToString().Trim() -split '\s+')[-1]
    if ($procId -match '^\d+$') { Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue }
  }
}

Write-Host '========================================' -ForegroundColor DarkYellow
Write-Host '  ESTIMASTRUCT  -  una sola ventana'       -ForegroundColor Yellow
Write-Host '========================================' -ForegroundColor DarkYellow

Write-Host '[1/3] Limpiando puertos 5000 y 8002...' -ForegroundColor DarkGray
Kill-Port 5000; Kill-Port 8002
Start-Sleep -Milliseconds 600

# Borrar bytecode cacheado (gotcha OneDrive+mtime: rutas nuevas no cargan)
Remove-Item (Join-Path $PROJECT 'backend\__pycache__'), (Join-Path $PROJECT 'backend\routers\__pycache__') -Recurse -Force -ErrorAction SilentlyContinue

Write-Host '[2/3] Verificando dependencias...' -ForegroundColor DarkGray
& $PY -c "import uvicorn, flask, fastapi, sqlalchemy, pydantic" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host '      faltan deps, instalando...' -ForegroundColor DarkGray
  & $PY -m pip install fastapi uvicorn sqlalchemy flask pydantic -q
}

Write-Host '[3/3] Iniciando servidores...' -ForegroundColor DarkGray
$back = Start-Job -Name back -ScriptBlock {
  param($py, $dir, $sbk)
  Set-Location $dir
  if ($sbk) { $env:SUPABASE_SECRET_KEY = $sbk }
  & $py -m uvicorn backend.main:app --host 127.0.0.1 --port 8002 --reload 2>&1
} -ArgumentList $PY, $PROJECT, $SUPABASE_SECRET_KEY

$front = Start-Job -Name front -ScriptBlock {
  param($py, $dir, $api)
  Set-Location $dir
  $env:ESTIMASTRUCT_API_BASE = $api
  & $py app.py 2>&1
} -ArgumentList $PY, (Join-Path $PROJECT 'ESTIMASTRUCT'), $API

Write-Host ''
Write-Host '  Frontend : http://localhost:5000/' -ForegroundColor Cyan
Write-Host '  Backend  : http://localhost:8002/' -ForegroundColor Magenta
Write-Host '  (cerrar esta ventana detiene los servidores)' -ForegroundColor DarkGray
Write-Host ''

function Drain($job, $tag, $color) {
  Receive-Job $job 2>$null | ForEach-Object {
    $line = ($_ | Out-String).Trim()
    if ($line) {
      Write-Host ("[{0}] {1} | " -f (Get-Date).ToString('HH:mm:ss'), $tag) -ForegroundColor $color -NoNewline
      Write-Host $line
    }
  }
}

try {
  while ($true) {
    Drain $back  'BACK ' Magenta
    Drain $front 'FRONT' Cyan
    if (($back.State -ne 'Running') -and ($front.State -ne 'Running')) { break }
    Start-Sleep -Milliseconds 350
  }
} finally {
  Drain $back  'BACK ' Magenta
  Drain $front 'FRONT' Cyan
  Stop-Job   $back, $front -ErrorAction SilentlyContinue
  Remove-Job $back, $front -Force -ErrorAction SilentlyContinue
  Kill-Port 5000; Kill-Port 8002
  Write-Host ''
  Write-Host 'Servidores detenidos.' -ForegroundColor Yellow
}
