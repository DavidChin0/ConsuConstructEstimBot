@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=python"
set "BACKEND=%ROOT%backend"

echo Verificando puerto 8002...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002 " ^| findstr LISTENING') do (
    echo Matando proceso existente en puerto 8002 (PID %%a)...
    taskkill /PID %%a /F >nul 2>&1
)

echo Instalando dependencias FastAPI...
cd /d "%BACKEND%"
%PYTHON% -m pip install -r "%ROOT%backend\requirements.txt" -q

echo.
echo ====================================
echo Iniciando Backend FastAPI en localhost:8002
echo ====================================
echo.

%PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload
