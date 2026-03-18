@echo off
cd /d "%~dp0\..\frontend"
set PATH=%PATH%;%USERPROFILE%\.cargo\bin
call npm run tauri dev
pause
