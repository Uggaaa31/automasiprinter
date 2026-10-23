@echo off
title "Hermes WhatsApp Tunnel"
color 0E
echo ===============================================================
echo                HERMES WHATSAPP TUNNEL
echo ===============================================================
echo.

cd /d "%~dp0"

where ngrok >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Menggunakan Ngrok Tunnel (Port 8000)...
    echo Salin URL HTTPS yang muncul (contoh: https://xxxx.ngrok-free.app)
    echo lalu tambahkan /webhook/fonnte di dashboard Fonnte.
    echo ===============================================================
    echo.
    ngrok http 8000
) else if exist "cloudflared.exe" (
    echo [INFO] Menggunakan Cloudflare Tunnel (Port 8000)...
    echo ===============================================================
    echo.
    cloudflared.exe tunnel --url http://localhost:8000
) else (
    echo [INFO] Menggunakan OpenSSH Tunnel (Port 443)...
    echo ===============================================================
    echo.
    ssh -p 443 -o StrictHostKeyChecking=no -R 80:localhost:8000 a.pinggy.io
)

pause
