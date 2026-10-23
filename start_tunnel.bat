@echo off
title Hermes WhatsApp Tunnel (Cloudflare)
color 0E
echo ===============================================================
echo           HERMES WHATSAPP TUNNEL (CLOUDFLARE)
echo ===============================================================
echo.

cd /d "%~dp0"

if exist "cloudflared.exe" (
    echo [INFO] Menghubungkan port 8000 ke internet via Cloudflare...
    echo.
    echo PETUNJUK:
    echo 1. Tunggu beberapa detik sampai muncul baris URL '.trycloudflare.com'.
    echo 2. Salin URL tersebut dan tambahkan /webhook/fonnte di belakangnya.
    echo    Contoh: https://xxxx.trycloudflare.com/webhook/fonnte
    echo 3. Tempel (Paste) URL tersebut di Webhook Dashboard Fonnte!
    echo ===============================================================
    echo.
    cloudflared.exe tunnel --url http://localhost:8000
) else (
    echo [INFO] cloudflared.exe tidak ditemukan di folder ini.
    echo Menggunakan fallback bawaan Windows (OpenSSH)...
    echo ===============================================================
    echo.
    ssh -R 80:localhost:8000 a.pinggy.io
)

pause
