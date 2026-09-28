@echo off
rem World Signal - gelistirme surumu baslaticisi.
rem Dagitim icin: .venv\Scripts\python tools\build.py  (sonuc: dist\WorldSignal)
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" goto setup
if not exist "frontend\dist\index.html" goto setup
goto run

:setup
echo.
echo  World Signal ilk kez hazırlanıyor. Bu işlem birkaç dakika sürebilir...
echo.
where uv >nul 2>nul
if errorlevel 1 (
  echo  HATA: "uv" programı bulunamadı. Bu mesajı Claude'a iletin.
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo  HATA: "Node.js / npm" bulunamadı. Bu mesajı Claude'a iletin.
  pause
  exit /b 1
)
uv sync --python 3.12
if errorlevel 1 goto fail
pushd frontend
call npm ci
if errorlevel 1 (
  popd
  goto fail
)
call npm run build
if errorlevel 1 (
  popd
  goto fail
)
popd

:run
start "" ".venv\Scripts\pythonw.exe" -m worldsignal
exit /b 0

:fail
echo.
echo  Hazırlık başarısız oldu. Yukarıdaki hata mesajını Claude'a iletin.
pause
exit /b 1
