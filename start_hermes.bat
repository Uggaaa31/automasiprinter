@echo off
title "Hermes Print Automation - Server"
color 0B
echo ===============================================================
echo            HERMES PRINT AUTOMATION - STARTING...
echo ===============================================================
echo.

cd /d "%~dp0"

:: 1. Deteksi dan Jalankan Tunnel di jendela terpisah
where ngrok >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Menjalankan Ngrok Tunnel di jendela terpisah...
    start "Hermes WhatsApp Tunnel (Ngrok)" cmd /k "ngrok http 8000"
) else if exist "cloudflared.exe" (
    echo [INFO] Menjalankan Cloudflare Tunnel di jendela terpisah...
    start "Hermes WhatsApp Tunnel (Cloudflare)" cmd /k "cloudflared.exe tunnel --url http://localhost:8000"
) else (
    echo [INFO] Menjalankan OpenSSH Tunnel di jendela terpisah...
    start "Hermes WhatsApp Tunnel (SSH)" cmd /k "ssh -p 443 -o StrictHostKeyChecking=no -R 80:localhost:8000 a.pinggy.io"
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
