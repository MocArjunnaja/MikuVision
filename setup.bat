@echo off
setlocal enabledelayedexpansion

echo ================================================
echo   MikuWin v4 Setup
echo   AI Assistant with RVC Voice (Hatsune Miku)
echo ================================================
echo.

echo [INFO] This setup script will install dependencies to your existing venv.
echo [INFO] Make sure your venv is activated before running this.
echo.

echo ================================================
echo   Option 1: Install base packages only
echo   (No RVC, uses Edge-TTS with Nanami voice)
echo.
echo   Run: pip install -r requirements.txt
echo.
echo ================================================
echo.
echo   Option 2: Install with RVC voice conversion
echo   (Advanced, has dependency issues on some systems)
echo.
echo   Run these manually in this order:
echo     1. pip install -r requirements.txt
echo     2. pip install rvc-python
echo     3. pip install torch==2.1.1+cu118 torchaudio==2.1.1+cu118 ^
echo        --index-url https://download.pytorch.org/whl/cu118
echo.
echo ================================================
echo.

echo To run MikuWin v4 after setup:
echo   1. Activate your venv
echo   2. python gui.py
echo.

pause
