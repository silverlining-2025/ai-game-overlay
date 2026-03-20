@echo off
chcp 65001 >nul 2>&1
title AI Gaming Companion — Tauri Dev
cd /d "%~dp0..\frontend"

echo.
echo  ============================================
echo   AI Gaming Companion — Tauri Dev Mode
echo  ============================================
echo.
echo  This starts the full Tauri app with hot reload.
echo  The config window will appear — enter your API
echo  key, select character/game, and click Start.
echo.
echo  API keys can be entered in the app UI directly.
echo  Press Ctrl+C to stop.
echo.

call npm run tauri dev

if errorlevel 1 (
    echo.
    echo  [ERROR] Tauri dev exited with an error.
    echo  Common fixes:
    echo    - Run scripts\1_setup.bat first
    echo    - Make sure Rust is installed (rustup.rs)
    echo    - Check that WebView2 is available
    pause
)
