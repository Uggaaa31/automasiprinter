@echo off
title "Hermes Print Automation - Server"
color 0B
echo ===============================================================
echo            HERMES PRINT AUTOMATION - STARTING...
echo ===============================================================
echo.

cd /d "%~dp0"

:: 1. Jalankan Gateway WhatsApp Lokal (Baileys - Gratis, Support File & Tanpa Tunnel)
echo [INFO] Menjalankan Gateway WhatsApp Lokal (Baileys) di jendela terpisah...
start "Hermes WhatsApp Gateway (Baileys)" cmd /k "cd /d \"%~dp0wa-gateway\" && npm start"

:: 2. Aktifkan Virtual Environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: 3. Jalankan Server FastAPI Uvicorn
echo.
echo [INFO] Menjalankan Server Hermes di http://localhost:8000 ...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
