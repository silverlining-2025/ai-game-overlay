@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Reset Data
cd /d "%~dp0.."

echo.
echo  ============================================
echo  Reset All Session Data
echo  ============================================
echo.
echo  This deletes training_data/ (sessions,
echo  companion memory, game DBs, screenshots).
echo.
echo  API keys and app settings are NOT affected.
echo.

set /p "CONFIRM=Type YES to confirm: "
if /i not "!CONFIRM!"=="YES" (
    echo  Cancelled.
    pause
    exit /b 0
)

echo.
if exist training_data (
    rmdir /s /q training_data
    echo  [OK] Deleted training_data/
) else (
    echo  [OK] Already clean
)

echo.
echo  Done. Next session starts fresh.
echo.
pause
