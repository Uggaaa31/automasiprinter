@echo off
title "Hermes Print Automation - Server"
color 0B
echo ===============================================================
echo            HERMES PRINT AUTOMATION - STARTING...
echo ===============================================================
echo.

cd /d "%~dp0"

:: 1. Jalankan Tunnel Publik via Windows OpenSSH (Gratis & Tanpa Login/Token)
echo [INFO] Menjalankan Tunnel Publik di jendela terpisah...
start "Hermes WhatsApp Tunnel" cmd /k "ssh -o StrictHostKeyChecking=no -R 80:localhost:8000 nokey@localhost.run"

:: 2. Aktifkan Virtual Environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: 3. Jalankan Server FastAPI Uvicorn
echo.
echo [INFO] Menjalankan Server Hermes di http://localhost:8000 ...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
