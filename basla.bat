@echo off
chcp 65001 >nul
set PYTHONUTF8=1
where py >nul 2>&1
if %errorlevel% neq 0 (
    echo HATA: Python kurulu degil!
    echo Lutfen https://www.python.org/downloads/ adresinden Python indirin.
    pause
    exit /b 1
)

echo Flask kuruluyor...
py -m pip install flask --quiet
echo.
echo ================================================
echo   Sapanca Ciftlik Restoran - Siparis Sistemi
echo ================================================
echo.
py app.py
pause
