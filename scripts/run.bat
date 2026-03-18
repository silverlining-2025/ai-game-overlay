@echo off
cd /d "%~dp0\..\frontend"
set PATH=%PATH%;%USERPROFILE%\.cargo\bin
npm run tauri dev
pause
