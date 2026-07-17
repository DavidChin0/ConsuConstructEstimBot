# EstimaStruct - lanzador en UNA sola ventana (backend 8002 + frontend 5000)
# Salida ordenada: [BACK ] magenta, [FRONT] cyan. Cerrar la ventana detiene todo.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { $PSNativeCommandUseErrorActionPreference = $false } catch {}
$Host.UI.RawUI.WindowTitle = 'EstimaStruct'

$PY       = 'D:\LLM\python\python.exe'
$PROJECT  = $PSScriptRoot   # portable: el lanzador vive en la raiz del repo
$API      = 'http://localhost:8002'

# Para el boton "Publicar a Portal": pega aca tu Supabase secret key (sb_secret_...).
# NO subir a git. Dejalo vacio si no vas a publicar.
$SUPABASE_SECRET_KEY = $env:SUPABASE_SECRET_KEY
# $SUPABASE_SECRET_KEY = 'sb_secret_xxxxxxxxxxxx'

function Kill-Tree([int]$rootPid) {
  # Kill all children recursively first, then the root
  $children = Get-WmiObject Win32_Process | Where-Object { $_.ParentProcessId -eq $rootPid }
  foreach ($child in $children) { Kill-Tree ([int]$child.ProcessId) }
  Stop-Process -Id $rootPid -Force -ErrorAction SilentlyContinue
}

function Kill-Port([int]$p) {
  # Round 1: kill via Get-NetTCPConnection (authoritative owner PID)
  $owners = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq 'Listen' } |
            Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($ownPid in $owners) { if ($ownPid -gt 0) { Kill-Tree $ownPid } }

  # Round 2: kill via netstat fallback (catches stale entries Get-NetTCPConnection misses)
  $hits = netstat -ano | Select-String (":{0}\s" -f $p) | Select-String 'LISTENING'
  foreach ($h in $hits) {
    $procId = ($h.ToString().Trim() -split '\s+')[-1]
    if ($procId -match '^\d+$') { Kill-Tree ([int]$procId) }
  }

  # Round 3: kill orphaned multiprocessing workers whose parent was a uvicorn on this port
  # (parent already dead, children hold the socket)
  Get-WmiObject Win32_Process | Where-Object {
    $_.CommandLine -like '*multiprocessing.spawn*' -or
    $_.CommandLine -like '*uvicorn*'
  } | ForEach-Object { Kill-Tree ([int]$_.ProcessId) }

  # Wait until port actually frees (max 3 s)
  $deadline = (Get-Date).AddSeconds(3)
  while ((Get-Date) -lt $deadline) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try { $tcp.Connect('127.0.0.1', $p); $tcp.Close(); Start-Sleep -Milliseconds 200 }
    catch { break }
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
& $PY -c "import uvicorn, flask, fastapi, sqlalchemy, pydantic, requests" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host '      faltan deps, instalando...' -ForegroundColor DarkGray
  & $PY -m pip install fastapi uvicorn sqlalchemy flask pydantic requests -q
}

Write-Host '[3/3] Iniciando servidores...' -ForegroundColor DarkGray
$back = Start-Job -Name back -ScriptBlock {
  param($py, $dir, $sbk)
  try { $PSNativeCommandUseErrorActionPreference = $false } catch {}
  Set-Location $dir
  if ($sbk) { $env:SUPABASE_SECRET_KEY = $sbk }
  & $py -m uvicorn backend.main:app --host 0.0.0.0 --port 8002 --reload 2>&1
} -ArgumentList $PY, $PROJECT, $SUPABASE_SECRET_KEY

$front = Start-Job -Name front -ScriptBlock {
  param($py, $dir, $api)
  try { $PSNativeCommandUseErrorActionPreference = $false } catch {}
  Set-Location $dir
  $env:ESTIMASTRUCT_API_BASE = $api
  & $py app.py 2>&1
} -ArgumentList $PY, (Join-Path $PROJECT 'ESTIMASTRUCT'), $API

Write-Host ''
Write-Host '  Frontend : http://localhost:5000/' -ForegroundColor Cyan
Write-Host '  Backend  : http://localhost:8002/' -ForegroundColor Magenta
Write-Host '  LAN UI    : http://192.168.x.x:5000/' -ForegroundColor DarkCyan
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

# Register-EngineEvent fires on window-close (X button) — finally only fires on Ctrl+C
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
  Stop-Job   $event.MessageData[0], $event.MessageData[1] -ErrorAction SilentlyContinue
  Remove-Job $event.MessageData[0], $event.MessageData[1] -Force -ErrorAction SilentlyContinue
  Kill-Port 5000; Kill-Port 8002
} -MessageData @($back, $front) | Out-Null

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
