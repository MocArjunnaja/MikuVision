@echo off
cd /d "%~dp0"

echo ================================================
echo   MikuVision - Hatsune Miku Edition
echo ================================================
echo.

rem Pakai env dari install.bat bila ada; selain itu python dari env yang sedang aktif
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" gui.py
) else (
    python gui.py
)
