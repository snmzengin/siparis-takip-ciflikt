@echo off
chcp 65001 >nul
set PYTHONUTF8=1
where py >nul 2>&1
if %errorlevel% neq 0 (
    echo HATA: Python kurulu degil!
    echo Lutfen https://www.python.org/downloads/ adresinden Python indirin.
    echo Kurulum ekraninda "Add python.exe to PATH" kutusunu isaretlemeyi unutma.
    pause
    exit /b 1
)

echo ================================================
echo   Sapanca Ciftlik Restoran - Yazici Koprusu
echo ================================================
echo.
py print_agent.py
pause
