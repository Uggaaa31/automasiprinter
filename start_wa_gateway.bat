@echo off
title "Hermes WhatsApp Gateway (Baileys)"
color 0A
echo ===============================================================
echo             HERMES WHATSAPP LOCAL GATEWAY (BAILEYS)
echo ===============================================================
echo.

cd /d "%~dp0wa-gateway"

if not exist "node_modules" (
    echo [INFO] Menginstal modul WhatsApp Gateway...
    call npm install
)

echo [INFO] Menjalankan WhatsApp Gateway di port 3001...
echo.
call npm start

pause
