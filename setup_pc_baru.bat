@echo off
setlocal enabledelayedexpansion
title Setup Hermes Print Automation - PC Baru
color 0A
echo ===============================================================
echo     HERMES PRINT AUTOMATION - SETUP OTOMATIS PC BARU
echo ===============================================================
echo.

cd /d "%~dp0"

:: -----------------------------------------------------------------
:: 1. PEMERIKSAAN & INSTALASI OTOMATIS PYTHON
:: -----------------------------------------------------------------
echo [1/5] Memeriksa instalasi Python di PC ini...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo       [INFO] Python belum terpasang. Memulai download & install otomatis...
    echo       Mengunduh installer resmi Python 3.12 (64-bit)...
    
    set "PY_URL=https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    set "PY_INSTALLER=%TEMP%\python_setup_temp.exe"
    
    curl.exe -L -o "!PY_INSTALLER!" "!PY_URL!"
    if not exist "!PY_INSTALLER!" (
        echo       Mencoba download cadangan via PowerShell...
        powershell -NoProfile -Command "Invoke-WebRequest -Uri '!PY_URL!' -OutFile '$env:TEMP\python_setup_temp.exe'"
    )
    
    if exist "!PY_INSTALLER!" (
        echo       Memasang Python 3.12 secara silent (Menambahkan ke PATH sistem)...
        start /wait "" "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 SimpleInstall=1
        del /f /q "!PY_INSTALLER!" >nul 2>&1
        echo       Python berhasil dipasang!
        
        :: Muat ulang PATH untuk sesi Command Prompt ini
        set "PATH=%LOCALAPPDATA%\Programs\Python\Python312;%LOCALAPPDATA%\Programs\Python\Python312\Scripts;%PATH%"
        for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "PATH=%%B;!PATH!"
    ) else (
        echo [ERROR] Gagal mengunduh installer Python. Pastikan PC terhubung ke internet.
        pause
        exit /b 1
    )
)

echo       Versi Python aktif:
python --version
if %errorlevel% neq 0 (
    echo [ERROR] Python belum terbaca di PATH. Silakan restart Command Prompt ini.
    pause
    exit /b 1
)

:: -----------------------------------------------------------------
:: 2. PEMERIKSAAN & INSTALASI OTOMATIS SUMATRAPDF (PRINT ENGINE)
:: -----------------------------------------------------------------
echo.
echo [2/5] Memeriksa SumatraPDF CLI untuk mesin pencetak...
if not exist "C:\Users\%USERNAME%\AppData\Local\SumatraPDF\SumatraPDF.exe" (
    if exist "SumatraPDF-3.6.1-64-install.exe" (
        echo       Memasang SumatraPDF secara silent...
        start /wait "" "SumatraPDF-3.6.1-64-install.exe" -s
        echo       SumatraPDF berhasil dipasang!
    ) else (
        echo       [INFO] Installer SumatraPDF lokal tidak ditemukan. Fallback PowerShell akan aktif.
    )
) else (
    echo       SumatraPDF sudah siap digunakan.
)

:: -----------------------------------------------------------------
:: 3. PEMERIKSAAN & DOWNLOAD OTOMATIS CLOUDFLARE TUNNEL (TUNNEL PUBLIK)
:: -----------------------------------------------------------------
echo.
echo [3/6] Memeriksa Cloudflare Tunnel (cloudflared.exe) untuk link publik Fonnte...
if not exist "cloudflared.exe" (
    echo       [INFO] cloudflared.exe belum ada. Mengunduh secara otomatis dari Cloudflare...
    set "CF_URL=https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    curl.exe -L -o "cloudflared.exe" "!CF_URL!"
    if not exist "cloudflared.exe" (
        echo       Mencoba download cadangan via PowerShell...
        powershell -NoProfile -Command "Invoke-WebRequest -Uri '!CF_URL!' -OutFile 'cloudflared.exe'"
    )
    if exist "cloudflared.exe" (
        echo       Cloudflare Tunnel berhasil diunduh dan siap digunakan!
    ) else (
        echo       [INFO] Gagal mengunduh cloudflared.exe. Anda tetap dapat menggunakan tunnel fallback via ssh bawaan Windows.
    )
) else (
    echo       Cloudflare Tunnel (cloudflared.exe) sudah siap digunakan.
)

:: -----------------------------------------------------------------
:: 4. MEMBUAT VIRTUAL ENVIRONMENT (VENV)
:: -----------------------------------------------------------------
echo.
echo [4/6] Menyiapkan Virtual Environment (venv) terisolasi...
if not exist "venv" (
    python -m venv venv
    echo       Virtual environment berhasil dibuat.
) else (
    echo       Virtual environment venv sudah ada.
)
call venv\Scripts\activate.bat

:: -----------------------------------------------------------------
:: 5. MENGINSTALL LIBRARY & DEPENDENSI PYTHON
:: -----------------------------------------------------------------
echo.
echo [5/6] Menginstall dependensi (FastAPI, PyMuPDF, GenAI/OpenAI, dll)...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt

:: -----------------------------------------------------------------
:: 6. MENYIAPKAN FILE KONFIGURASI .ENV
:: -----------------------------------------------------------------
echo.
echo [6/6] Memeriksa konfigurasi environment (.env)...
if not exist ".env" (
    if exist ".env.example" (
        copy .env.example .env >nul
        echo       File .env baru telah dibuat dari template. Silakan lengkapi token Fonnte.
    )
) else (
    echo       File .env sudah ada.
)

echo.
echo ===============================================================
echo   🎉 SETUP SELESAI 100%! PC INI SIAP MENJALANKAN HERMES PRINT.
echo.
echo   Langkah Selanjutnya:
echo   1. Pastikan file .env sudah berisi token WhatsApp Fonnte Anda.
echo   2. Klik 2x file 'start_hermes.bat' untuk langsung memulai server + tunnel!
echo ===============================================================
echo.
pause
