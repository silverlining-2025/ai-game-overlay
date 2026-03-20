@echo off
setlocal
chcp 65001 >nul 2>&1
title Build - AI Gaming Companion
cd /d "%~dp0.."

echo.
echo  ============================================
echo  Production Build
echo  ============================================
echo.

echo  [1/3] PyInstaller sidecar...
cd backend
python -m PyInstaller web_overlay.spec --clean --noconfirm
if errorlevel 1 (
    echo  [ERROR] PyInstaller failed
    pause
    exit /b 1
)
cd ..
echo  [OK] Sidecar built
echo.

echo  [2/3] Vite frontend...
cd frontend
call npm run build
if errorlevel 1 (
    echo  [ERROR] Vite build failed
    pause
    exit /b 1
)
echo  [OK] Frontend built
echo.

echo  [3/3] Tauri installer...
call npm run tauri build
if errorlevel 1 (
    echo  [ERROR] Tauri build failed
    pause
    exit /b 1
)
cd ..

echo.
echo  ============================================
echo  Build complete!
echo  Installer: frontend\src-tauri\target\release\bundle\nsis\
echo  ============================================
echo.
pause
