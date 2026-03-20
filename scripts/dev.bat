@echo off
REM ============================================================
REM Dev mode: runs backend + frontend in development
REM ============================================================

echo.
echo   AI Gaming Companion — Dev Mode
echo   Backend: http://localhost:8080
echo   Frontend: Tauri dev window
echo.

cd /d "%~dp0..\frontend"
npm run tauri dev
