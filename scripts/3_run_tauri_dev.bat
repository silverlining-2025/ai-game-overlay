@echo off
setlocal
chcp 65001 >nul 2>&1
title Tauri Dev - AI Gaming Companion
cd /d "%~dp0..\frontend"

echo.
echo  ============================================
echo  Tauri Dev Mode
echo  ============================================
echo.
echo  Config window will open.
echo  Enter API key in the app, pick character,
echo  click Start.
echo.
echo  Press Ctrl+C to stop.
echo.

call npm run tauri dev

if errorlevel 1 (
    echo.
    echo  [ERROR] Tauri dev failed.
    echo  Run scripts\1_setup.bat first.
    pause
)
