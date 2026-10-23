@echo off
title Hermes Print Automation - Server & Tunnel
color 0B
echo ===============================================================
echo            HERMES PRINT AUTOMATION - STARTING...
echo ===============================================================
echo.

cd /d "%~dp0"

:: 1. Jalankan Cloudflare Tunnel di jendela terpisah jika file tersedia
if exist "cloudflared.exe" (
    echo [INFO] Menjalankan Cloudflare Tunnel di jendela terpisah...
    start "Hermes WhatsApp Tunnel (Cloudflare)" cmd /k "cloudflared.exe tunnel --url http://localhost:8000"
) else (
    echo [INFO] cloudflared.exe belum ada.
    echo Anda dapat menjalankan tunnel fallback via ssh: ssh -R 80:localhost:8000 a.pinggy.io
)

:: 2. Aktifkan Virtual Environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

:: 3. Jalankan Server FastAPI Uvicorn
echo.
echo [INFO] Menjalankan Server Hermes di http://localhost:8000 ...
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
