@echo off
chcp 65001 >nul
rem TTYSI kadastr sayti - Windows'da ishga tushirish.
rem Ikki marta bosing. Birinchi marta kerakli kutubxonalar o'rnatiladi.
rem Binolar papkasi: shu faylga parametr sifatida bering yoki standart "Hujjatlar\TTYSI Binolar".

cd /d "%~dp0.."
where python >nul 2>nul || (
  echo Python topilmadi. python.org dan Python 3.12 ni o'rnating ^("Add Python to PATH" belgisi bilan^).
  pause
  exit /b 1
)

set "WS=%~1"
if "%WS%"=="" set "WS=%USERPROFILE%\Documents\TTYSI Binolar"

if not exist ".venv-web\Scripts\python.exe" (
  echo Birinchi ishga tushirish: kutubxonalar o'rnatilmoqda...
  python -m venv .venv-web || (pause & exit /b 1)
  ".venv-web\Scripts\python.exe" -m pip install -q -r web\requirements.txt || (pause & exit /b 1)
)

echo.
echo Binolar papkasi: %WS%
echo Kompyuterda:  http://localhost:8000
echo Telefonda:    http://^<shu kompyuter IP manzili^>:8000   ^(ipconfig - IPv4 Address^)
echo Birinchi marta shu kompyuterda http://localhost:8000 ni ochib, administrator yarating.
echo To'xtatish: Ctrl+C
echo.
start "" http://localhost:8000
".venv-web\Scripts\python.exe" -m web.server --workspace "%WS%" --host 0.0.0.0 --port 8000
pause
