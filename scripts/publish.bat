@echo off
chcp 65001 >nul
setlocal EnableExtensions
title World Signal - GitHub'da Yayinla

echo ==========================================
echo   WORLD SIGNAL YENI SURUMU GITHUB'DA YAYINLA
echo ==========================================
echo.
echo   Once scripts\clean-build-release.bat ile paket hazirlanmis olmali.
echo   Deneme icin (gondermeden): scripts\publish.bat --dry-run
echo.

cd /d "%~dp0.."
set "PYEXE=.venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo   HATA: Python ortami yok. Once scripts\clean-build-release.bat calistirin.
    pause
    exit /b 1
)

"%PYEXE%" tools\publish.py %*
if errorlevel 1 (
    echo.
    echo   Yayin tamamlanamadi. Ayrintilar yukarida.
    pause
    exit /b 1
)
echo.
pause
exit /b 0
