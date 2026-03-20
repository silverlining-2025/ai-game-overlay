@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Setup
cd /d "%~dp0.."

echo.
echo  ============================================
echo  Setup - AI Gaming Companion
echo  ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.11+
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo  [OK] %%i

where node >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Node.js not found. Install from nodejs.org
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do echo  [OK] Node %%i

echo.
echo  Installing Python dependencies...
pip install -r backend\requirements.txt -q
if errorlevel 1 (
    echo  [ERROR] pip install failed
    pause
    exit /b 1
)
echo  [OK] Python deps installed

echo.
echo  Installing frontend dependencies...
cd frontend
call npm install --silent 2>nul
if errorlevel 1 (
    echo  [ERROR] npm install failed
    pause
    exit /b 1
)
cd ..
echo  [OK] Frontend deps installed

echo.
echo  Running tests...
python -X utf8 -m pytest backend/tests/ -q 2>&1
if errorlevel 1 (
    echo  [WARN] Some tests failed
) else (
    echo  [OK] All tests passed
)

echo.
echo  ============================================
echo  Setup complete!
echo.
echo  Next steps:
echo    1. Get a free Gemini API key:
echo       https://aistudio.google.com/apikey
echo.
echo    2. Set it:
echo       set GEMINI_API_KEY=your-key-here
echo.
echo    3. Run:
echo       scripts\2_run_backend.bat
echo  ============================================
echo.
pause
