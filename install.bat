@echo off
rem Installer MikuVision: double-click file ini. Argumen diteruskan ke install.ps1 (contoh: install.bat -Yes -Cpu)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set "CODE=%ERRORLEVEL%"
echo.
if "%CODE%"=="0" (echo Instalasi selesai.) else (echo Instalasi GAGAL. Lihat log di folder logs\)
pause
exit /b %CODE%
