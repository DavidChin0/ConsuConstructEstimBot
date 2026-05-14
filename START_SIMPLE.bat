@echo off
REM Script simple para levantar Frontend + Backend en dos consolas
REM Instalación automática de dependencias

setlocal enabledelayedexpansion

set "ROOT=%~dp0"
set "PYTHON=python"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%ESTIMASTRUCT"
set ESTIMASTRUCT_API_BASE=http://localhost:8002

echo.
echo ========================================
echo ESTIMASTRUCT — Iniciando Servidores
echo ========================================
echo.

REM Limpiar puertos
echo [1/4] Limpiando puertos 5000 y 8002...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5000 " ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002 " ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
timeout /t 1 /nobreak >nul

REM Instalar dependencias
echo [2/4] Instalando dependencias (esto puede tardar)...
%PYTHON% -m pip install -r "%ROOT%backend\requirements.txt" -q
echo.

REM Levantar Backend (ventana abierta permanente)
echo [3/4] Iniciando Backend FastAPI en puerto 8002...
start "ESTIMASTRUCT Backend (8002)" /D "%BACKEND%" %PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload

REM Dar tiempo para que backend se levante
timeout /t 3 /nobreak >nul

REM Levantar Frontend (ventana abierta permanente)
echo [4/4] Iniciando Frontend Flask en puerto 5000...
start "ESTIMASTRUCT Frontend (5000)" /D "%FRONTEND%" %PYTHON% app.py

echo.
echo ========================================
echo [OK] Servidores iniciados
echo ========================================
echo.
echo Acceso:
echo   Frontend:  http://localhost:5000/
echo   Backend:   http://localhost:8002/
echo.
echo Dos consolas abiertas automáticamente
echo (ciérralas cuando termines)
echo.
pause
