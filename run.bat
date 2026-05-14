@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=python"
set "BACKEND=%ROOT%backend"

cd /d "%BACKEND%"
%PYTHON% -m pip install -r "%ROOT%backend\requirements.txt" -q
%PYTHON% seed_bd.py
%PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8002 --reload
