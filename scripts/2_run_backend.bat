@echo off
chcp 65001 >nul 2>&1
title AI Gaming Companion — Backend
cd /d "%~dp0.."

echo.
echo  ============================================
echo   AI Gaming Companion — Backend Mode
echo   URL: http://localhost:8080
echo  ============================================
echo.

REM Check for at least one API key
if not defined ANTHROPIC_API_KEY (
    if not defined GEMINI_API_KEY (
        if not defined OPENAI_API_KEY (
            echo  [WARNING] No API key found in environment.
            echo.
            echo  Set at least one:
            echo    set GEMINI_API_KEY=AIza-your-key    (free!)
            echo    set ANTHROPIC_API_KEY=sk-ant-...    (paid)
            echo    set OPENAI_API_KEY=sk-...           (paid)
            echo.
            echo  Get a free Gemini key: https://aistudio.google.com/apikey
            echo.
            set /p "GEMINI_API_KEY=Enter Gemini API key (or press Enter to skip): "
            if not defined GEMINI_API_KEY (
                echo  [ERROR] No API key provided. Cannot start.
                pause
                exit /b 1
            )
        )
    )
)

REM Show which keys are active
echo  API Keys:
if defined GEMINI_API_KEY echo    [OK] Gemini (free tier)
if defined ANTHROPIC_API_KEY echo    [OK] Anthropic (Claude)
if defined OPENAI_API_KEY echo    [OK] OpenAI (GPT-4o-mini)
echo.

REM Parse optional arguments
set GAME=palworld
set CHAR=nozomi
set TIER=free
set LOCALE=ko

if not "%1"=="" set GAME=%1
if not "%2"=="" set CHAR=%2
if not "%3"=="" set TIER=%3
if not "%4"=="" set LOCALE=%4

echo  Config: game=%GAME% character=%CHAR% tier=%TIER% locale=%LOCALE%
echo  Press Ctrl+C to stop
echo.

python -X utf8 -m backend.tools.web_overlay ^
    --game %GAME% ^
    --character %CHAR% ^
    --tier %TIER% ^
    --locale %LOCALE% ^
    --port 8080 ^
    --interval 3

if errorlevel 1 (
    echo.
    echo  [ERROR] Backend exited with an error. Check output above.
    pause
)
