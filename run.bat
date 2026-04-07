@echo off
cd /d "%~dp0"

echo ================================================
echo   MikuWin v4 - Hatsune Miku Edition
echo ================================================
echo.

REM Assume user's venv is already activated
REM If not, activate it first

python gui.py
