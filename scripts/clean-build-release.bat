@echo off
chcp 65001 >nul
setlocal EnableExtensions
title World Signal - Temizle + Test + Derle + Release Hazirla

echo ==================================================
echo   WORLD SIGNAL  TEMIZLE + TEST + DERLE + RELEASE
echo ==================================================
echo.

cd /d "%~dp0.."
set "PYEXE=.venv\Scripts\python.exe"

rem Derlenmis program calisiyorsa dist klasoru kilitli olur ve silinemez.
tasklist /FI "IMAGENAME eq WorldSignal.exe" 2>nul | find /I "WorldSignal.exe" >nul
if not errorlevel 1 (
    echo   UYARI: World Signal su an acik. Tepsideki simgeye sag tiklayip Cikis'i secin,
    echo   sonra bu pencerede bir tusa basin.
    pause
)

echo [1/6] Eski derleme klasorleri temizleniyor...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "frontend\dist" rmdir /s /q "frontend\dist"
if exist "dist" (
    echo   HATA: dist klasoru silinemedi ^(bir dosyasi kullanimda^). Programi kapatip tekrar deneyin.
    pause
    exit /b 1
)
echo   Tamam.
echo.

echo [2/6] Gerekli araclar ve kutuphaneler kontrol ediliyor...
where uv >nul 2>nul
if errorlevel 1 (
    echo   HATA: "uv" bulunamadi. Bu mesaji Claude'a iletin.
    pause
    exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
    echo   HATA: "Node.js / npm" bulunamadi. Bu mesaji Claude'a iletin.
    pause
    exit /b 1
)
uv sync --python 3.12
if errorlevel 1 (
    echo   HATA: Python kutuphaneleri kurulamadi.
    pause
    exit /b 1
)
pushd frontend
call npm ci --no-audit --no-fund
if errorlevel 1 (
    popd
    echo   HATA: Arayuz kutuphaneleri kurulamadi.
    pause
    exit /b 1
)
popd
echo   Tamam.
echo.

echo [3/6] Testler calistiriliyor (birkac dakika surer)...
pushd frontend
call npm test
if errorlevel 1 (
    popd
    echo   HATA: Arayuz testleri basarisiz. Release hazirlama durduruldu.
    pause
    exit /b 1
)
call npm run build
if errorlevel 1 (
    popd
    echo   HATA: Arayuz derlenemedi.
    pause
    exit /b 1
)
popd
"%PYEXE%" -m pytest -q -p no:cacheprovider
if errorlevel 1 (
    echo.
    echo   HATA: Arka uc testleri basarisiz. Release hazirlama durduruldu.
    echo   Not: Bu bilgisayarda Python ara ara "access violation" ile cokebiliyor. Hata buysa
    echo   betigi bir kez daha calistirin; baska bir hataysa bu pencereyi Claude'a iletin.
    pause
    exit /b 1
)
echo   Tamam.
echo.

echo [4/6] Kaynak yedegi aliniyor...
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set TS=%%i
if not exist "backups" mkdir "backups"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$items = Get-ChildItem -Force ^| Where-Object { $_.Name -notin @('.git','.venv','backups','build','dist','release','.devdata','.pytest_cache','__pycache__','.claude') }; $items = $items ^| ForEach-Object { if ($_.Name -eq 'frontend') { Get-ChildItem $_.FullName -Force ^| Where-Object { $_.Name -notin @('node_modules','dist','coverage') } } else { $_ } }; Compress-Archive -Path $items.FullName -DestinationPath 'backups\WorldSignal_Kaynak_%TS%.zip' -Force; Get-ChildItem 'backups\WorldSignal_Kaynak_*.zip' ^| Sort-Object LastWriteTime -Descending ^| Select-Object -Skip 3 ^| Remove-Item -Force"
if errorlevel 1 (
    echo   HATA: Kaynak yedegi alinamadi.
    pause
    exit /b 1
)
echo   backups\WorldSignal_Kaynak_%TS%.zip
echo.

echo [5/6] Program derleniyor (PyInstaller)...
set "BUILD_OK="
for /l %%n in (1,1,3) do (
    if not defined BUILD_OK (
        "%PYEXE%" tools\build.py --skip-ui && set "BUILD_OK=1"
        if not defined BUILD_OK echo   Deneme %%n basarisiz, yeniden deneniyor...
    )
)
if not defined BUILD_OK (
    echo   HATA: Derleme 3 denemede de basarisiz oldu.
    pause
    exit /b 1
)
echo.

echo [6/6] Surum paketi (zip) hazirlaniyor ve dogrulaniyor...
"%PYEXE%" tools\release.py
if errorlevel 1 (
    echo   HATA: Release hazirlanamadi. Ayrintilar yukarida.
    pause
    exit /b 1
)
echo.
echo ==================================================
echo   TAMAMLANDI. GitHub'da yayinlamak icin: scripts\publish.bat
echo ==================================================
echo.
pause
exit /b 0
