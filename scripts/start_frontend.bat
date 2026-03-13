@echo off
echo [AI Game Overlay] Starting frontend...
cd /d "%~dp0..\frontend"

if not exist "node_modules" (
    echo Installing npm dependencies...
    npm install
)

echo Starting Tauri dev server...
npm run tauri dev
pause
