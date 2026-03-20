@echo off
REM ============================================================
REM Backend only: runs the Python overlay with browser UI
REM Opens http://localhost:8080 automatically
REM ============================================================

echo.
echo   AI Gaming Companion — Backend Only (Browser)
echo   URL: http://localhost:8080
echo.

cd /d "%~dp0.."
python -X utf8 -m backend.tools.web_overlay --game palworld --character nozomi --tier free %*
