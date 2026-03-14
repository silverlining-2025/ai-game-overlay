@echo off
echo === Building AI Game Overlay .exe ===
echo.

cd /d %~dp0..

pip install pyinstaller --quiet 2>nul

cd backend
pyinstaller web_overlay.spec --clean --noconfirm

:: Create data directory with defaults
if not exist dist\ai-game-overlay\data mkdir dist\ai-game-overlay\data
copy data\*.txt dist\ai-game-overlay\data\ >nul 2>&1

:: Create .env template
echo ANTHROPIC_API_KEY=your-key-here> dist\ai-game-overlay\.env.example

:: Create run script
(
echo @echo off
echo if not exist ".env" (
echo     echo ERROR: Create a .env file with your ANTHROPIC_API_KEY
echo     echo Copy .env.example to .env and add your key
echo     pause
echo     exit /b 1
echo ^)
echo echo Starting AI Companion Overlay...
echo echo Open http://localhost:8080 in your browser
echo echo Press Ctrl+C to stop
echo ai-game-overlay.exe --game maplestory --interval 3
echo pause
) > dist\ai-game-overlay\run.bat

echo.
echo === Build complete ===
echo Output: backend\dist\ai-game-overlay\
echo.
echo To distribute:
echo   1. Copy the backend\dist\ai-game-overlay\ folder to a USB
echo   2. On target PC: rename .env.example to .env, add API key
echo   3. Double-click run.bat
echo.
pause
