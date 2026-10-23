@echo off
title "Hermes WhatsApp Tunnel"
color 0E
echo ===============================================================
echo                HERMES WHATSAPP TUNNEL
echo ===============================================================
echo.

cd /d "%~dp0"

echo [INFO] Menghubungkan port 8000 ke internet via Windows OpenSSH...
echo.
echo PETUNJUK:
echo 1. Tunggu 1-2 detik sampai muncul baris 'https://xxxx.lhr.life'.
echo 2. Salin URL tersebut dan tambahkan /webhook/fonnte di belakangnya:
echo    Contoh: https://xxxx.lhr.life/webhook/fonnte
echo 3. Tempel (Paste) URL tersebut di kolom 'Webhook ?' di Dashboard Fonnte!
echo ===============================================================
echo.
ssh -o StrictHostKeyChecking=no -R 80:127.0.0.1:8000 nokey@localhost.run

pause
