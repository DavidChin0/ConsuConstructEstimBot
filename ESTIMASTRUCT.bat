@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=python"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%ESTIMASTRUCT"
set "REQ=%ROOT%backend\requirements.txt"
set "ESTIMASTRUCT_API_BASE=http://localhost:8002"

where python >nul 2>nul
if errorlevel 1 (
  where py >nul 2>nul
  if not errorlevel 1 (
    set "PYTHON=py -3"
  ) else (
    echo No se encontro Python en PATH.
    echo Instala Python o agrega python.exe al PATH.
    pause
    exit /b 1
  )
)

echo.
echo ========================================
echo ESTIMASTRUCT - Iniciando app completa
echo ========================================
echo.

echo [1/3] Instalando dependencias...
%PYTHON% -m pip install -r "%REQ%" -q
if errorlevel 1 (
  echo Error instalando dependencias.
  pause
  exit /b 1
)

echo [2/3] Iniciando Backend FastAPI en 8002...
start "ESTIMASTRUCT Backend (8002)" /D "%BACKEND%" %PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload

timeout /t 3 /nobreak >nul

echo [3/3] Iniciando Frontend Flask en 5000...
start "ESTIMASTRUCT Frontend (5000)" /D "%FRONTEND%" %PYTHON% app.py

echo.
echo ========================================
echo [OK] Servidores iniciados
echo ========================================
echo Frontend: http://localhost:5000/
echo Backend:  http://localhost:8002/
echo ========================================
echo.
pause
