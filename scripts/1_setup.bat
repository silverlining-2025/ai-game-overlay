@echo off
chcp 65001 >nul 2>&1
title AI Gaming Companion — Setup
cd /d "%~dp0.."

echo.
echo  ============================================
echo   AI Gaming Companion — Environment Setup
echo  ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found. Install Python 3.11+ from python.org
    pause
    exit /b 1
)
echo  [OK] Python found
python --version

REM Check Node
node --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Node.js not found. Install from nodejs.org
    pause
    exit /b 1
)
echo  [OK] Node.js found

REM Install Python dependencies
echo.
echo  Installing Python dependencies...
pip install -r backend\requirements.txt -q
if errorlevel 1 (
    echo  [ERROR] pip install failed
    pause
    exit /b 1
)
echo  [OK] Python dependencies installed

REM Install frontend dependencies
echo.
echo  Installing frontend dependencies...
cd frontend
call npm install --silent
if errorlevel 1 (
    echo  [ERROR] npm install failed
    pause
    exit /b 1
)
cd ..
echo  [OK] Frontend dependencies installed

REM Run tests
echo.
echo  Running tests...
python -X utf8 -m pytest backend/tests/ -q 2>&1
if errorlevel 1 (
    echo  [WARN] Some tests failed — check output above
) else (
    echo  [OK] All tests passed
)

REM Clean stale test data
python -X utf8 -c "import shutil; [shutil.rmtree(f'training_data/{d}', ignore_errors=True) for d in ['_test_game','_test_','_test_pkg_']]" 2>nul

echo.
echo  ============================================
echo   Setup complete! Next steps:
echo.
echo   1. Set your API key:
echo      set GEMINI_API_KEY=AIza-your-key
echo      (Get free key: https://aistudio.google.com/apikey)
echo.
echo   2. Run one of:
echo      scripts\2_run_backend.bat    (browser overlay)
echo      scripts\3_run_tauri_dev.bat  (full Tauri app)
echo      scripts\4_run_tests.bat      (test suite)
echo  ============================================
echo.
pause
