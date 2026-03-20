@echo off
REM ============================================================
REM Full build: PyInstaller sidecar + Tauri installer
REM Output: frontend\src-tauri\target\release\bundle\nsis\*.exe
REM ============================================================

echo.
echo ============================================
echo   AI Gaming Companion — Full Build
echo ============================================
echo.

REM Step 1: Build Python sidecar
echo [1/3] Building Python sidecar (PyInstaller)...
cd /d "%~dp0..\backend"
python -m PyInstaller web_overlay.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed
    exit /b 1
)
echo       Sidecar built: dist\ai-companion\

REM Step 2: Build frontend
echo [2/3] Building frontend (Vite)...
cd /d "%~dp0..\frontend"
call npm run build
if errorlevel 1 (
    echo ERROR: Vite build failed
    exit /b 1
)
echo       Frontend built: dist\

REM Step 3: Build Tauri installer
echo [3/3] Building Tauri installer...
call npm run tauri build
if errorlevel 1 (
    echo ERROR: Tauri build failed
    exit /b 1
)

echo.
echo ============================================
echo   Build complete!
echo ============================================
echo.
echo   Installer: frontend\src-tauri\target\release\bundle\nsis\
echo   Sidecar:   backend\dist\ai-companion\
echo.
