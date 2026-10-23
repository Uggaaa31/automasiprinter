@echo off
title Hermes Print Automation - Running
color 0B
echo ===============================================================
echo            HERMES PRINT AUTOMATION - STARTING...
echo ===============================================================
echo.

cd /d "%~dp0"

if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
