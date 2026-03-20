@echo off
chcp 65001 >nul 2>&1
title AI Gaming Companion — Reset Data
cd /d "%~dp0.."

echo.
echo  ============================================
echo   AI Gaming Companion — Reset Session Data
echo  ============================================
echo.
echo  This will delete ALL training data, session
echo  recordings, companion memory, and game DBs.
echo.
echo  Your API keys (in environment) are NOT affected.
echo  Your app settings (in localStorage) are NOT affected.
echo.

set /p CONFIRM="  Type YES to confirm: "
if /i not "%CONFIRM%"=="YES" (
    echo  Cancelled.
    pause
    exit /b 0
)

echo.
if exist training_data (
    echo  Removing training_data/...
    rmdir /s /q training_data
    echo  [OK] Deleted
) else (
    echo  [OK] No training_data/ found (already clean)
)

echo.
echo  Data reset complete. Next session starts fresh.
echo.
pause
